"""Analisis pola gempa: magnitudo, kedalaman, waktu, energi, dan kedekatan
dengan gunung api.

Semua fungsi menerima ``DataFrame`` berkolom standar (lihat ``sumber.KOLOM_GEMPA``)
dan tidak menyentuh jaringan ataupun Streamlit, sehingga dapat diuji sendiri.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

ZONA_WIB = "Asia/Jakarta"
RADIUS_BUMI_KM = 6371.0

# Energi gempa (Gutenberg-Richter, 1956): log10 E[J] = 1.5 M + 4.8
# Bom Hiroshima ~ 15 kiloton TNT ~ 6,3 x 10^13 joule.
ENERGI_HIROSHIMA_J = 6.3e13

BATAS_KEDALAMAN = [(70, "Dangkal (<70 km)"), (300, "Menengah (70–300 km)"), (math.inf, "Dalam (>300 km)")]
URUTAN_KEDALAMAN = [nama for _, nama in BATAS_KEDALAMAN]


# ---------------------------------------------------------------------------
# Kolom turunan
# ---------------------------------------------------------------------------

def kelas_kedalaman(km: float | None) -> str:
    """Kelas kedalaman seismologi: dangkal, menengah, dalam."""
    # Kedalaman negatif atau tak hingga (sel rusak) bukan "dangkal" atau "dalam"; perlakukan seperti kosong.
    if km is None or pd.isna(km) or not math.isfinite(km) or km < 0:
        return "Tidak diketahui"
    for batas, nama in BATAS_KEDALAMAN:
        if km < batas:
            return nama
    return URUTAN_KEDALAMAN[-1]


def energi_joule(magnitudo: float) -> float:
    """Energi seismik yang dilepaskan, dalam joule."""
    return 10 ** (1.5 * magnitudo + 4.8)


def setara_hiroshima(joule: float) -> float:
    return joule / ENERGI_HIROSHIMA_J


def tambah_kolom(df: pd.DataFrame) -> pd.DataFrame:
    """Tambahkan kolom turunan yang dipakai grafik dan peta."""
    df = df.copy()
    if df.empty:
        for k in ("kelas_kedalaman", "energi_joule", "waktu_wib", "jam_wib", "tanggal_wib"):
            df[k] = pd.Series(dtype="object")
        return df
    df["kelas_kedalaman"] = df["kedalaman_km"].map(kelas_kedalaman)
    df["energi_joule"] = df["magnitudo"].map(energi_joule)
    # Waktu tanpa zona (misalnya dari CSV) dianggap UTC; format ISO campuran tetap terbaca.
    df["waktu_wib"] = _ke_utc(df["waktu_utc"]).dt.tz_convert(ZONA_WIB)
    df["jam_wib"] = df["waktu_wib"].dt.hour
    df["tanggal_wib"] = df["waktu_wib"].dt.date
    return df


# ---------------------------------------------------------------------------
# Ringkasan
# ---------------------------------------------------------------------------

def _waktu_utc(df: pd.DataFrame) -> pd.DataFrame:
    """Samakan `waktu_utc` jadi bertimezone UTC; waktu naive (mis. dari CSV) dianggap UTC.

    Tanpa ini, membandingkan dengan `pd.Timestamp.now(tz="UTC")` melempar TypeError.
    """
    return df.assign(waktu_utc=_ke_utc(df["waktu_utc"]))


def _ke_utc(waktu: pd.Series) -> pd.Series:
    """Teks/datetime jadi datetime UTC. Format ISO campuran ("...T09:00" dan "... 10:00", atau
    dengan offset +07:00) tetap terbaca; tanpa format="ISO8601" pandas menebak format dari baris
    pertama dan baris lain yang beda format diam-diam jadi NaT."""
    return pd.to_datetime(waktu, errors="coerce", utc=True, format="ISO8601")


def _sekarang(sekarang: pd.Timestamp | None) -> pd.Timestamp:
    if sekarang is None:
        return pd.Timestamp.now(tz="UTC")
    sekarang = pd.Timestamp(sekarang)
    return sekarang.tz_localize("UTC") if sekarang.tzinfo is None else sekarang.tz_convert("UTC")


def ringkasan(df: pd.DataFrame, sekarang: pd.Timestamp | None = None) -> dict:
    """Angka-angka utama untuk kartu KPI."""
    if df.empty:
        return {"jumlah": 0}
    df = _waktu_utc(df)
    sekarang = _sekarang(sekarang)
    terbaru = df.sort_values("waktu_utc", ascending=False).iloc[0]
    # Magnitudo inf (sel rusak) jangan jadi "gempa terbesar" dan membuat total energi tak hingga.
    df = df.assign(magnitudo=pd.to_numeric(df["magnitudo"], errors="coerce").replace([np.inf, -np.inf], np.nan))
    terbesar = df.sort_values("magnitudo", ascending=False).iloc[0]
    selisih = (df["waktu_utc"].max() - df["waktu_utc"].min()).total_seconds() / 86400
    # Tanpa waktu yang valid selisihnya NaN, dan max(NaN, x) tetap NaN; pakai batas minimal 1 jam.
    rentang_hari = max(selisih, 1 / 24) if pd.notna(selisih) else 1 / 24
    energi_total = float(df["magnitudo"].map(energi_joule).sum())
    return {
        "jumlah": len(df),
        "rentang_hari": rentang_hari,
        "per_hari": len(df) / rentang_hari,
        "terbaru": terbaru,
        "menit_sejak_terbaru": (sekarang - terbaru["waktu_utc"]).total_seconds() / 60,
        "terbesar": terbesar,
        "m_maks": float(terbesar["magnitudo"]),
        "m_median": float(df["magnitudo"].median()),
        "kedalaman_median": float(df["kedalaman_km"].median()),
        # Persen dihitung dari gempa yang kedalamannya diketahui saja;
        # kedalaman kosong bukan berarti "tidak dangkal".
        "persen_dangkal": float((df["kedalaman_km"].dropna() < 70).mean() * 100)
        if df["kedalaman_km"].notna().any() else float("nan"),
        "energi_total_j": energi_total,
        "energi_hiroshima": setara_hiroshima(energi_total),
    }


def denyut(df: pd.DataFrame, jam: int = 24, sekarang: pd.Timestamp | None = None) -> dict:
    """Bandingkan jumlah gempa ``jam`` terakhir dengan rata-rata jendela data.

    Rasio > 1 berarti bumi sedang "berdenyut" lebih cepat dari biasanya.
    """
    if df.empty:
        return {"terakhir": 0, "rata_rata": 0.0, "rasio": 0.0}
    # Gempa tanpa waktu tidak bisa ditempatkan di jendela mana pun; kalau semuanya kosong,
    # rentang_jam jadi NaN dan rasio ikut NaN (max(NaN, jam) tetap NaN).
    df = _waktu_utc(df).dropna(subset=["waktu_utc"])
    if df.empty:
        return {"terakhir": 0, "rata_rata": 0.0, "rasio": 0.0}
    sekarang = _sekarang(sekarang)
    batas = sekarang - pd.Timedelta(hours=jam)
    terakhir = int((df["waktu_utc"] >= batas).sum())
    rentang_jam = max((sekarang - df["waktu_utc"].min()).total_seconds() / 3600, jam)
    rata = len(df) / rentang_jam * jam
    return {"terakhir": terakhir, "rata_rata": rata, "rasio": terakhir / rata if rata else 0.0}


# ---------------------------------------------------------------------------
# Magnitudo: Gutenberg-Richter dan b-value
# ---------------------------------------------------------------------------

def _periksa_positif(nilai: float, nama: str) -> None:
    """Lebar bin/kotak nol membuat pembagian tak hingga; negatif membalik pusat kotak."""
    if not (nilai > 0 and math.isfinite(nilai)):
        raise ValueError(f"{nama} harus bilangan positif, bukan {nilai!r}")


def magnitudo_lengkap(mag: pd.Series, lebar_bin: float = 0.1) -> float:
    """Perkiraan magnitudo kelengkapan (Mc) dengan metode kelengkungan maksimum:
    bin magnitudo dengan jumlah gempa terbanyak. Magnitudo kosong diabaikan."""
    _periksa_positif(lebar_bin, "lebar_bin")
    # Magnitudo tak hingga (sel rusak) tidak bisa dibulatkan ke bin; abaikan seperti NaN.
    mag = mag[np.isfinite(pd.to_numeric(mag, errors="coerce"))]
    if mag.empty:
        return float("nan")
    bins = (mag / lebar_bin).round().astype(int)
    return float(bins.value_counts().idxmax() * lebar_bin)


def b_value(mag: pd.Series, mc: float | None = None, lebar_bin: float = 0.1) -> dict:
    """b-value Gutenberg-Richter dengan penaksir kemungkinan maksimum Aki (1965):

        b = log10(e) / (mean(M) - (Mc - lebar_bin / 2))

    Nilai b ~ 1 adalah normal untuk zona subduksi. b yang jauh lebih kecil
    berarti proporsi gempa besar lebih tinggi dari biasanya; b yang besar
    sering muncul pada kawanan gempa vulkanik.
    """
    # Mc yang diberikan langsung melewati magnitudo_lengkap, jadi lebar_bin tetap harus dicek di sini;
    # lebar 0 dengan semua gempa tepat di Mc membuat pembaginya nol.
    _periksa_positif(lebar_bin, "lebar_bin")
    # Magnitudo inf membuat rata-rata inf dan b jadi 0; buang seperti di magnitudo_lengkap.
    mag = mag[np.isfinite(pd.to_numeric(mag, errors="coerce"))]
    if mc is None:
        mc = magnitudo_lengkap(mag, lebar_bin)
    terpakai = mag[mag >= mc - 1e-9]
    n = len(terpakai)
    if n < 2:
        return {"b": float("nan"), "a": float("nan"), "mc": mc, "n": n, "galat": float("nan")}
    rata = float(terpakai.mean())
    b = math.log10(math.e) / (rata - (mc - lebar_bin / 2))
    galat = 2.30 * b * b * float(terpakai.std(ddof=1)) / math.sqrt(n) if n > 1 else float("nan")  # Shi & Bolt (1982), bentuk ringkas
    a = math.log10(n) + b * mc
    return {"b": b, "a": a, "mc": mc, "n": n, "galat": galat}


def gutenberg_richter(mag: pd.Series, lebar_bin: float = 0.1) -> pd.DataFrame:
    """Tabel frekuensi kumulatif: untuk setiap M, berapa gempa dengan magnitudo >= M."""
    _periksa_positif(lebar_bin, "lebar_bin")
    mag = mag[np.isfinite(pd.to_numeric(mag, errors="coerce"))]
    if mag.empty:
        return pd.DataFrame(columns=["magnitudo", "jumlah_kumulatif", "log10_n"])
    # Batas dibangun dari bilangan bulat kelipatan lebar_bin; membulatkan ke 1 desimal
    # membuat bin 0,05 jadi ganda (4,0; 4,0; 4,1; 4,1; ...).
    awal = math.floor(round(mag.min() / lebar_bin, 9))
    akhir = math.ceil(round(mag.max() / lebar_bin, 9))
    batas = np.round(np.arange(awal, akhir + 1) * lebar_bin, 6)
    jumlah = [(mag >= m - 1e-9).sum() for m in batas]
    df = pd.DataFrame({"magnitudo": batas, "jumlah_kumulatif": jumlah})
    df = df[df["jumlah_kumulatif"] > 0]
    df["log10_n"] = np.log10(df["jumlah_kumulatif"])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Waktu
# ---------------------------------------------------------------------------

def per_hari(df: pd.DataFrame) -> pd.DataFrame:
    """Jumlah gempa dan magnitudo maksimum per tanggal (WIB)."""
    if df.empty:
        return pd.DataFrame(columns=["tanggal", "jumlah", "m_maks"])
    d = tambah_kolom(df) if "tanggal_wib" not in df else df
    g = d.groupby("tanggal_wib").agg(jumlah=("magnitudo", "size"), m_maks=("magnitudo", "max")).reset_index()
    g = g.rename(columns={"tanggal_wib": "tanggal"})
    # Semua waktu kosong (NaT) dibuang groupby; date_range(NaT, NaT) lalu melempar ValueError.
    if g.empty:
        return pd.DataFrame(columns=["tanggal", "jumlah", "m_maks"])
    semua = pd.date_range(g["tanggal"].min(), g["tanggal"].max(), freq="D").date
    g = g.set_index("tanggal").reindex(semua).fillna({"jumlah": 0}).rename_axis("tanggal").reset_index()
    g["jumlah"] = g["jumlah"].astype(int)
    return g


def per_jam(df: pd.DataFrame) -> pd.DataFrame:
    """Jumlah gempa per jam WIB (0-23). Dipakai untuk menunjukkan bahwa bumi
    tidak mengenal siang dan malam."""
    d = tambah_kolom(df) if "jam_wib" not in df else df
    hitung = d["jam_wib"].value_counts().reindex(range(24), fill_value=0).sort_index() if not d.empty else pd.Series(0, index=range(24))
    return pd.DataFrame({"jam": hitung.index, "jumlah": hitung.values.astype(int)})


def jeda_antar_gempa(df: pd.DataFrame) -> pd.Series:
    """Selisih waktu (menit) antara gempa berurutan."""
    if len(df) < 2:
        return pd.Series(dtype=float)
    # Waktu dari CSV masih berupa teks; diff() pada teks melempar TypeError.
    w = _waktu_utc(df)["waktu_utc"].sort_values()
    return (w.diff().dropna().dt.total_seconds() / 60).reset_index(drop=True)


def energi_kumulatif(df: pd.DataFrame) -> pd.DataFrame:
    """Energi yang dilepaskan secara kumulatif sepanjang waktu, dalam joule
    dan dalam satuan "bom Hiroshima"."""
    if df.empty:
        return pd.DataFrame(columns=["waktu_utc", "magnitudo", "energi_j", "kumulatif_j", "kumulatif_hiroshima"])
    # Urutkan menurut waktu sebenarnya, bukan teks: "2026-01-01 10:00" lebih kecil dari "2026-01-01T09:00"
    # kalau dibandingkan sebagai string, sehingga garis kumulatif bisa mundur.
    d = _waktu_utc(df[["waktu_utc", "magnitudo"]]).sort_values("waktu_utc", kind="mergesort")
    # Gempa tanpa magnitudo dihitung 0 joule supaya garis kumulatif tidak putus;
    # magnitudo inf (sel rusak) juga, kalau tidak seluruh garis sesudahnya jadi inf.
    d["energi_j"] = d["magnitudo"].map(energi_joule).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    d["kumulatif_j"] = d["energi_j"].cumsum()
    d["kumulatif_hiroshima"] = d["kumulatif_j"] / ENERGI_HIROSHIMA_J
    return d.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Ruang: jarak, gunung api terdekat, zona aktif
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    """Jarak lingkaran besar; menerima skalar maupun array numpy."""
    lat1, lon1, lat2, lon2 = map(np.radians, (np.asarray(lat1, float), np.asarray(lon1, float), np.asarray(lat2, float), np.asarray(lon2, float)))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * RADIUS_BUMI_KM * np.arcsin(np.sqrt(a))


def gunung_terdekat(gempa: pd.DataFrame, gunung: pd.DataFrame) -> pd.DataFrame:
    """Untuk tiap gempa: nama gunung api terdekat dan jaraknya (km)."""
    df = gempa.copy()
    if df.empty or gunung.empty:
        df["gunung_terdekat"] = pd.Series(dtype="object")
        df["jarak_gunung_km"] = pd.Series(dtype=float)
        return df
    jarak = haversine_km(df["lat"].values[:, None], df["lon"].values[:, None], gunung["lat"].values[None, :], gunung["lon"].values[None, :])
    # Gempa tanpa koordinat menghasilkan baris jarak NaN semua; argmin lalu
    # menunjuk indeks 0 sehingga gunung pertama di daftar ikut terpasang.
    ada = ~np.isnan(jarak).all(axis=1)
    idx = np.where(ada, np.nanargmin(np.where(np.isnan(jarak), np.inf, jarak), axis=1), 0)
    df["gunung_terdekat"] = np.where(ada, gunung["nama"].values[idx], None)
    df["jarak_gunung_km"] = np.where(ada, jarak[np.arange(len(df)), idx], np.nan)
    return df


def gempa_sekitar_gunung(gempa: pd.DataFrame, gunung: pd.DataFrame, radius_km: float = 50.0) -> pd.DataFrame:
    """Jumlah gempa dalam radius tertentu dari tiap gunung api, beserta
    magnitudo maksimumnya. Gempa dangkal dekat gunung api sering berkaitan
    dengan pergerakan magma, meski tidak selalu."""
    if gempa.empty or gunung.empty:
        return gunung.assign(jumlah_gempa=0, m_maks=np.nan)
    jarak = haversine_km(gunung["lat"].values[:, None], gunung["lon"].values[:, None], gempa["lat"].values[None, :], gempa["lon"].values[None, :])
    dalam = jarak <= radius_km
    mag = gempa["magnitudo"].to_numpy(dtype=float)
    # Magnitudo inf (sel rusak) jangan jadi m_maks gunung; anggap kosong seperti di ringkasan.
    mag = np.where(np.isfinite(mag), mag, np.nan)
    hasil = gunung.copy()
    hasil["jumlah_gempa"] = dalam.sum(axis=1).astype(int)
    # nanmax: satu gempa tanpa magnitudo tidak boleh membuat m_maks ikut NaN.
    hasil["m_maks"] = [
        float(np.nanmax(mag[baris])) if np.isfinite(mag[baris]).any() else np.nan for baris in dalam
    ]
    return hasil.sort_values(["jumlah_gempa", "level"], ascending=False).reset_index(drop=True)


def zona_aktif(df: pd.DataFrame, ukuran_derajat: float = 2.0, teratas: int = 8) -> pd.DataFrame:
    """Kelompokkan gempa ke kotak ``ukuran_derajat`` x ``ukuran_derajat`` dan
    urutkan dari yang paling ramai. Label diambil dari nama wilayah yang
    paling sering muncul di kotak itu."""
    _periksa_positif(ukuran_derajat, "ukuran_derajat")
    if df.empty:
        return pd.DataFrame(columns=["lat", "lon", "jumlah", "m_maks", "kedalaman_median", "label"])
    d = df.copy()
    d["magnitudo"] = pd.to_numeric(d["magnitudo"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    d["_r"] = (d["lat"] // ukuran_derajat) * ukuran_derajat + ukuran_derajat / 2
    d["_c"] = (d["lon"] // ukuran_derajat) * ukuran_derajat + ukuran_derajat / 2
    g = (
        d.groupby(["_r", "_c"])
        .agg(
            jumlah=("magnitudo", "size"),
            m_maks=("magnitudo", "max"),
            kedalaman_median=("kedalaman_km", "median"),
            label=("wilayah", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
        )
        .reset_index()
        .rename(columns={"_r": "lat", "_c": "lon"})
    )
    # Kotak dengan jumlah sama diurutkan menurut lat/lon supaya hasilnya tetap; head(-n) dicegah.
    g = g.sort_values(["jumlah", "lat", "lon"], ascending=[False, True, True], kind="mergesort")
    return g.head(max(teratas, 0)).reset_index(drop=True)
