"""Pengambilan dan normalisasi data gempa serta gunung api.

Tiga sumber publik dipakai:

* **BMKG** (data.bmkg.go.id): 15 gempa M5+ terkini dan gempa yang dirasakan.
* **USGS** (earthquake.usgs.gov, FDSN event API): katalog gempa global yang
  dipotong dengan kotak koordinat Indonesia.
* **MAGMA Indonesia** (magma.esdm.go.id): tingkat aktivitas gunung api
  (Level I Normal sampai Level IV Awas), dibaca dari halaman HTML publik.

Setiap fungsi ``ambil_*`` mengembalikan ``DataFrame`` dengan kolom yang sama,
sehingga lapisan analisis dan peta tidak perlu tahu dari mana data berasal.
Jika jaringan gagal, ``muat_semua`` jatuh ke berkas contoh di ``data/sample``.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DIR_DATA = Path(__file__).resolve().parent.parent / "data"
DIR_SAMPLE = DIR_DATA / "sample"

URL_BMKG_TERKINI = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json"
URL_BMKG_DIRASAKAN = "https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json"
URL_USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
URL_MAGMA = "https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas"

# Kotak koordinat Indonesia, sedikit dilebihkan agar gempa di perbatasan ikut.
KOTAK_INDONESIA = {"minlatitude": -12.0, "maxlatitude": 7.0, "minlongitude": 94.0, "maxlongitude": 142.0}

KOLOM_GEMPA = ["id", "waktu_utc", "lat", "lon", "magnitudo", "kedalaman_km", "wilayah", "sumber", "keterangan", "url"]

TIMEOUT = 20
HEADERS = {"User-Agent": "ring-of-fire-pulse/1.0 (proyek edukasi; data publik)"}


@dataclass
class HasilMuat:
    """Hasil ``muat_semua``: data plus catatan dari mana data itu berasal."""

    gempa: pd.DataFrame
    gunung_api: pd.DataFrame
    sumber_gempa: dict[str, str] = field(default_factory=dict)
    sumber_gunung: str = ""
    offline: bool = False
    waktu_ambil: datetime | None = None
    kesalahan: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser murni (tanpa jaringan) agar mudah diuji
# ---------------------------------------------------------------------------

def _angka(teks: str | float | None) -> float | None:
    """Ambil angka pertama dari teks seperti ``"10 km"`` atau ``"5.3"``."""
    if teks is None or isinstance(teks, bool):
        return None
    if isinstance(teks, (int, float)):
        # NaN/inf dianggap kosong supaya pemeriksaan "is None" di parser tetap jalan.
        return float(teks) if math.isfinite(teks) else None
    cocok = re.search(r"-?\d+(?:[.,]\d+)?", str(teks))
    return float(cocok.group(0).replace(",", ".")) if cocok else None


def _angka_teks(teks: str) -> float | None:
    """Teks yang seluruhnya angka ("4.5"); "4.5 km" atau "x" dianggap kosong."""
    try:
        nilai = float(teks)
    except ValueError:
        return None
    return nilai if math.isfinite(nilai) else None


def _bingkai_kosong() -> pd.DataFrame:
    df = pd.DataFrame({k: pd.Series(dtype="object") for k in KOLOM_GEMPA})
    df["waktu_utc"] = pd.to_datetime(df["waktu_utc"], utc=True)
    for k in ("lat", "lon", "magnitudo", "kedalaman_km"):
        df[k] = df[k].astype(float)
    return df


def parse_bmkg(payload: dict, label: str = "BMKG") -> pd.DataFrame:
    """Ubah JSON BMKG (``gempaterkini`` / ``gempadirasakan``) menjadi DataFrame."""
    gempa = payload.get("Infogempa", {}).get("gempa", [])
    if isinstance(gempa, dict):  # autogempa.json berisi satu objek, bukan daftar
        gempa = [gempa]
    baris = []
    for g in gempa:
        koord = str(g.get("Coordinates", "")).split(",")
        if len(koord) != 2:
            continue
        lat, lon = _angka(koord[0]), _angka(koord[1])
        waktu = g.get("DateTime")
        if lat is None or lon is None or not waktu:
            continue
        # Lintang di luar ±90 atau bujur di luar ±180 (koordinat tertukar/rusak) tidak bisa dipetakan.
        if abs(lat) > 90 or abs(lon) > 180:
            continue
        baris.append(
            {
                "id": f"bmkg-{waktu}-{lat}-{lon}",
                "waktu_utc": waktu,
                "lat": lat,
                "lon": lon,
                "magnitudo": _angka(g.get("Magnitude")),
                "kedalaman_km": _angka(g.get("Kedalaman")),
                # Field bisa ada tapi bernilai null; str(None) akan menulis "None" sebagai wilayah.
                "wilayah": str(g.get("Wilayah") or "").strip(),
                "sumber": label,
                "keterangan": str(g.get("Dirasakan") or g.get("Potensi") or "").strip(),
                "url": "https://www.bmkg.go.id/gempabumi/",
            }
        )
    if not baris:
        return _bingkai_kosong()
    df = pd.DataFrame(baris, columns=KOLOM_GEMPA)
    df["waktu_utc"] = pd.to_datetime(df["waktu_utc"], utc=True, errors="coerce")
    return df.dropna(subset=["waktu_utc", "magnitudo"]).reset_index(drop=True)


def parse_usgs(geojson: dict) -> pd.DataFrame:
    """Ubah GeoJSON USGS menjadi DataFrame. Kedalaman ada di koordinat ketiga."""
    baris = []
    for f in geojson.get("features") or []:
        # properties/geometry bisa bernilai null di GeoJSON; `or {}` supaya .get tidak gagal.
        p = f.get("properties") or {}
        koord = (f.get("geometry") or {}).get("coordinates") or []
        # Magnitudo teks rusak ("x") atau inf dilewati, bukan menggagalkan seluruh katalog.
        mag = _angka_teks(p.get("mag")) if isinstance(p.get("mag"), str) else _angka(p.get("mag"))
        if len(koord) < 3 or mag is None or p.get("time") is None:
            continue
        if _angka(koord[0]) is None or _angka(koord[1]) is None:
            continue
        # Waktu rusak (teks, inf) dilewati; satu baris saja dulu menggagalkan seluruh katalog.
        waktu = p.get("time")
        waktu_ms = _angka_teks(waktu) if isinstance(waktu, str) else _angka(waktu)
        if waktu_ms is None:
            continue
        baris.append(
            {
                "id": f.get("id"),
                "waktu_utc": pd.Timestamp(int(waktu_ms), unit="ms", tz="UTC"),
                "lat": float(koord[1]),
                "lon": float(koord[0]),
                "magnitudo": mag,
                # Kedalaman null dibiarkan kosong (NaN) agar gempanya tetap tercatat.
                "kedalaman_km": _angka(koord[2]),
                "wilayah": p.get("place") or "",
                "sumber": "USGS",
                # Field bisa ada tapi bernilai null; `or ""` supaya tidak tertulis "None".
                "keterangan": f"{p.get('magType') or ''} · {p.get('status') or ''}".strip(" ·"),
                "url": p.get("url") or "",
            }
        )
    if not baris:
        return _bingkai_kosong()
    df = pd.DataFrame(baris, columns=KOLOM_GEMPA)
    df["waktu_utc"] = pd.to_datetime(df["waktu_utc"], utc=True)
    return df.reset_index(drop=True)


_POLA_LEVEL = re.compile(r'class="tx-inverse[^"]*">\s*Level (I{1,3}|IV) \(([A-Za-z]+)\)\s*</a>')
_POLA_BARIS = re.compile(r"<td>\s*([^<]+?)\s*<a href=\"(https://magma\.esdm\.go\.id/v1/gunung-api/laporan/\d+)")
LEVEL_ANGKA = {"I": 1, "II": 2, "III": 3, "IV": 4}
LEVEL_NAMA = {1: "Normal", 2: "Waspada", 3: "Siaga", 4: "Awas"}


def parse_magma(html: str) -> pd.DataFrame:
    """Baca tabel "Daftar Tingkat Aktivitas Gunung Api" dari halaman MAGMA.

    Hasil: kolom ``nama``, ``provinsi``, ``level`` (1-4), ``status``, ``url_laporan``.
    Nama seperti "Lewotobi Laki-laki - Nusa Tenggara Timur" dipisah pada
    tanda " - " terakhir agar tanda hubung di dalam nama tidak ikut terpotong.
    """
    potongan = _POLA_LEVEL.split(html)
    baris = []
    for i in range(1, len(potongan), 3):
        level, status, isi = potongan[i], potongan[i + 1], potongan[i + 2]
        for teks, url in _POLA_BARIS.findall(isi):
            teks = " ".join(teks.split())
            if " - " in teks:
                nama, provinsi = teks.rsplit(" - ", 1)
            else:
                nama, provinsi = teks, ""
            baris.append(
                {
                    "nama": nama.strip(),
                    "provinsi": provinsi.strip(),
                    "level": LEVEL_ANGKA[level],
                    "status": status,
                    "url_laporan": url,
                }
            )
    return pd.DataFrame(baris, columns=["nama", "provinsi", "level", "status", "url_laporan"])


# ---------------------------------------------------------------------------
# Pengambilan dari jaringan
# ---------------------------------------------------------------------------

def _get_json(url: str, params: dict | None = None) -> dict:
    r = requests.get(url, params=params, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def ambil_bmkg_terkini() -> pd.DataFrame:
    return parse_bmkg(_get_json(URL_BMKG_TERKINI), "BMKG M5+")


def ambil_bmkg_dirasakan() -> pd.DataFrame:
    return parse_bmkg(_get_json(URL_BMKG_DIRASAKAN), "BMKG dirasakan")


def ambil_usgs(hari: int = 30, magnitudo_min: float = 2.5, limit: int = 20000) -> pd.DataFrame:
    mulai = (datetime.now(UTC) - timedelta(days=hari)).strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        "format": "geojson",
        "starttime": mulai,
        "minmagnitude": magnitudo_min,
        "orderby": "time",
        "limit": limit,
        **KOTAK_INDONESIA,
    }
    return parse_usgs(_get_json(URL_USGS, params))


def ambil_magma() -> pd.DataFrame:
    r = requests.get(URL_MAGMA, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    df = parse_magma(r.text)
    if df.empty:
        raise ValueError("Tabel tingkat aktivitas MAGMA tidak ditemukan di halaman")
    return df


# ---------------------------------------------------------------------------
# Gabungan, deduplikasi, dan fallback offline
# ---------------------------------------------------------------------------

def gabung_gempa(*bingkai: pd.DataFrame) -> pd.DataFrame:
    """Satukan beberapa katalog dan buang duplikat lintas sumber.

    Dua kejadian dari sumber BERBEDA dianggap sama bila selisih waktunya
    paling lama 2 menit dan selisih lintang/bujurnya paling jauh setengah
    derajat. Baris USGS dipertahankan lebih dulu karena katalognya paling
    lengkap; BMKG melengkapi gempa yang tidak ada di USGS. Gempa dari sumber
    yang sama tidak pernah dibuang (gempa susulan bisa berdekatan sekali).
    """
    isi = [b for b in bingkai if b is not None and not b.empty]
    if not isi:
        return _bingkai_kosong()
    df = pd.concat(isi, ignore_index=True)
    urutan = {"USGS": 0, "BMKG M5+": 1, "BMKG dirasakan": 2}
    df["_urut"] = df["sumber"].map(urutan).fillna(9)
    df = df.sort_values(["_urut", "waktu_utc"]).reset_index(drop=True)
    # Bandingkan selisih langsung, bukan ember waktu/koordinat yang dibulatkan:
    # 01:59:59 dan 02:00:01 jatuh di ember berbeda padahal hanya terpaut 2 detik.
    # total_seconds tidak bergantung satuan internal (pandas 3 memakai mikrodetik,
    # sehingga astype("int64") // 10**9 bukan lagi detik).
    detik = (df["waktu_utc"] - pd.Timestamp(0, tz="UTC")).dt.total_seconds().to_numpy()
    lat = df["lat"].to_numpy(dtype=float)
    lon = df["lon"].to_numpy(dtype=float)
    sumber_baris = df["sumber"].to_numpy()
    simpan = np.ones(len(df), dtype=bool)
    for i in range(len(df)):
        lebih_dulu = simpan[:i] & (sumber_baris[:i] != sumber_baris[i])
        if not lebih_dulu.any():
            continue
        sama = (
            lebih_dulu
            & (np.abs(detik[:i] - detik[i]) <= 120)
            & (np.abs(lat[:i] - lat[i]) <= 0.5)
            & (np.abs(lon[:i] - lon[i]) <= 0.5)
        )
        if sama.any():
            simpan[i] = False
    df = df[simpan].drop(columns=["_urut"])
    return df.sort_values("waktu_utc", ascending=False).reset_index(drop=True)


def muat_gunung_api_statis() -> pd.DataFrame:
    """Daftar 69 gunung api yang dipantau MAGMA beserta koordinatnya."""
    return pd.read_csv(DIR_DATA / "gunung_api.csv")


def _kunci(s: pd.Series) -> pd.Series:
    return s.str.lower().str.replace(r"[^a-z]", "", regex=True)


def gabung_gunung_api(statis: pd.DataFrame, level: pd.DataFrame | None) -> pd.DataFrame:
    """Tempelkan level aktivitas MAGMA ke daftar koordinat statis."""
    df = statis.copy()
    if level is None or level.empty:
        df["level"] = 1
        df["status"] = "Normal"
        df["url_laporan"] = ""
        return df
    df["_k"] = _kunci(df["nama"])
    lvl = level.copy()
    lvl["_k"] = _kunci(lvl["nama"])
    # Nama kosong tidak boleh jadi kunci: merge pandas mencocokkan NaN dengan NaN.
    lvl = lvl[lvl["_k"].fillna("") != ""].drop_duplicates("_k")
    df = df.merge(lvl[["_k", "level", "status", "url_laporan"]], on="_k", how="left").drop(columns="_k")
    df["level"] = df["level"].fillna(1).astype(int)
    df["status"] = df["status"].fillna("Normal")
    df["url_laporan"] = df["url_laporan"].fillna("")
    return df


def muat_sample() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Baca berkas contoh yang disimpan di ``data/sample``."""
    meta = json.loads((DIR_SAMPLE / "meta.json").read_text(encoding="utf-8"))
    usgs = parse_usgs(json.loads((DIR_SAMPLE / "usgs.json").read_text(encoding="utf-8")))
    terkini = parse_bmkg(json.loads((DIR_SAMPLE / "bmkg_terkini.json").read_text(encoding="utf-8")), "BMKG M5+")
    dirasakan = parse_bmkg(json.loads((DIR_SAMPLE / "bmkg_dirasakan.json").read_text(encoding="utf-8")), "BMKG dirasakan")
    level = pd.read_csv(DIR_SAMPLE / "magma_level.csv")
    gempa = gabung_gempa(usgs, terkini, dirasakan)
    gunung = gabung_gunung_api(muat_gunung_api_statis(), level)
    return gempa, gunung, meta


def muat_semua(hari: int = 30, magnitudo_min: float = 2.5, paksa_offline: bool = False) -> HasilMuat:
    """Ambil semua sumber; sumber yang gagal diganti dengan data contoh.

    Setiap sumber ditangani sendiri-sendiri: bila USGS sukses tetapi MAGMA
    gagal, hanya gunung api yang memakai data contoh. ``offline`` bernilai
    True bila ada minimal satu sumber yang jatuh ke data contoh.
    """
    sample_gempa, sample_gunung, meta = muat_sample()
    hasil = HasilMuat(gempa=_bingkai_kosong(), gunung_api=sample_gunung, waktu_ambil=datetime.now(UTC))
    if paksa_offline:
        hasil.gempa = sample_gempa
        hasil.offline = True
        hasil.sumber_gempa = {"semua": f"data contoh ({meta['diambil']})"}
        hasil.sumber_gunung = f"data contoh ({meta['diambil']})"
        return hasil

    bagian = []
    for nama, fn in (
        ("USGS", lambda: ambil_usgs(hari=hari, magnitudo_min=magnitudo_min)),
        ("BMKG M5+", ambil_bmkg_terkini),
        ("BMKG dirasakan", ambil_bmkg_dirasakan),
    ):
        try:
            bagian.append(fn())
            hasil.sumber_gempa[nama] = "langsung"
        except Exception as e:  # noqa: BLE001 - semua kegagalan jaringan diperlakukan sama
            hasil.kesalahan.append(f"{nama}: {e}")
            hasil.sumber_gempa[nama] = "gagal"
            hasil.offline = True
    hasil.gempa = gabung_gempa(*bagian)
    if hasil.gempa.empty:
        hasil.gempa = sample_gempa
        hasil.sumber_gempa = {"semua": f"data contoh ({meta['diambil']})"}
        hasil.offline = True

    try:
        level = ambil_magma()
        hasil.gunung_api = gabung_gunung_api(muat_gunung_api_statis(), level)
        hasil.sumber_gunung = "langsung"
    except Exception as e:  # noqa: BLE001
        hasil.kesalahan.append(f"MAGMA: {e}")
        hasil.sumber_gunung = f"data contoh ({meta['diambil']})"
        hasil.offline = True
    return hasil
