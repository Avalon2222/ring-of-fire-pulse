"""Pengujian parser dan penggabungan data. Tidak memerlukan jaringan."""

import json

import pandas as pd
import pytest

from src import sumber

CONTOH_BMKG = {
    "Infogempa": {
        "gempa": [
            {
                "Tanggal": "30 Okt 2026",
                "Jam": "03:32:13 WIB",
                "DateTime": "2026-10-29T20:32:13+00:00",
                "Coordinates": "-4.40,132.49",
                "Magnitude": "5.3",
                "Kedalaman": "10 km",
                "Wilayah": "139 km BaratLaut TUAL-MALUKU",
                "Potensi": "Tidak berpotensi tsunami",
            },
            {"DateTime": "2026-10-29T03:26:49+00:00", "Coordinates": "rusak", "Magnitude": "6.0", "Kedalaman": "120 km"},
        ]
    }
}

CONTOH_USGS = {
    "features": [
        {
            "id": "us7000abcd",
            "properties": {"mag": 4.3, "place": "Banda Sea", "time": 1793452208987, "url": "https://x", "magType": "mb", "status": "reviewed"},
            "geometry": {"coordinates": [128.9289, -6.4305, 254.829]},
        },
        {"id": "tanpa-mag", "properties": {"mag": None, "time": 1}, "geometry": {"coordinates": [0, 0, 0]}},
    ]
}

CONTOH_MAGMA = """
<tr><td rowspan="1"><a href="" class="tx-inverse tx-14 tx-medium d-block">Level IV (Awas)</a></td><td>0</td>
<td>Tidak ada gunung api Level IV (Awas)</td></tr>
<tr><td rowspan="2"><a href="" class="tx-inverse tx-14 tx-medium d-block">Level III (Siaga)</a></td></tr>
<tr><td>
    Lewotobi Laki-laki - Nusa Tenggara Timur <a href="https://magma.esdm.go.id/v1/gunung-api/laporan/1?signature=x"><i></i>Lihat laporan</a><br>
</td></tr>
<tr><td rowspan="2"><a href="" class="tx-inverse tx-14 tx-medium d-block">Level I (Normal)</a></td></tr>
<tr><td>
    Agung - Bali <a href="https://magma.esdm.go.id/v1/gunung-api/laporan/2?signature=y"><i></i>Lihat laporan</a><br>
</td></tr>
"""


def test_angka_mengambil_angka_dari_teks():
    assert sumber._angka("10 km") == 10.0
    assert sumber._angka("5,3") == 5.3
    assert sumber._angka(4) == 4.0
    assert sumber._angka(None) is None
    assert sumber._angka("tidak ada") is None
    assert sumber._angka(float("nan")) is None
    assert sumber._angka(float("inf")) is None
    assert sumber._angka(True) is None


def test_parse_bmkg_melewati_koordinat_nan():
    payload = {"Infogempa": {"gempa": [
        {"Coordinates": "nan,106.5", "DateTime": "2026-11-01T00:00:00+00:00", "Magnitude": "5.1", "Kedalaman": "10 km"},
        {"Coordinates": "-6.1,106.5", "DateTime": "2026-11-01T01:00:00+00:00", "Magnitude": "5.2", "Kedalaman": "10 km"},
    ]}}
    df = sumber.parse_bmkg(payload)
    assert len(df) == 1
    assert df.iloc[0]["lat"] == -6.1


def test_parse_bmkg_membaca_koordinat_dan_kedalaman():
    df = sumber.parse_bmkg(CONTOH_BMKG, "BMKG M5+")
    assert list(df.columns) == sumber.KOLOM_GEMPA
    assert len(df) == 1, "baris dengan koordinat rusak harus dibuang"
    r = df.iloc[0]
    assert (r["lat"], r["lon"]) == (-4.40, 132.49)
    assert r["kedalaman_km"] == 10.0
    assert r["magnitudo"] == 5.3
    assert r["sumber"] == "BMKG M5+"
    assert str(r["waktu_utc"].tz) == "UTC"


def test_parse_bmkg_menerima_objek_tunggal_autogempa():
    tunggal = {"Infogempa": {"gempa": CONTOH_BMKG["Infogempa"]["gempa"][0]}}
    assert len(sumber.parse_bmkg(tunggal)) == 1


def test_parse_usgs_mengambil_kedalaman_dari_koordinat_ketiga():
    df = sumber.parse_usgs(CONTOH_USGS)
    assert len(df) == 1
    r = df.iloc[0]
    assert r["lat"] == pytest.approx(-6.4305)
    assert r["lon"] == pytest.approx(128.9289)
    assert r["kedalaman_km"] == pytest.approx(254.829)
    assert r["waktu_utc"] == pd.Timestamp(1793452208987, unit="ms", tz="UTC")


def test_parse_kosong_mengembalikan_bingkai_berkolom_lengkap():
    df = sumber.parse_usgs({"features": []})
    assert df.empty and list(df.columns) == sumber.KOLOM_GEMPA
    assert str(df["waktu_utc"].dtype).startswith("datetime64")


def test_parse_magma_memisahkan_nama_dan_provinsi():
    df = sumber.parse_magma(CONTOH_MAGMA)
    assert len(df) == 2
    lewotobi = df[df["nama"] == "Lewotobi Laki-laki"].iloc[0]
    assert lewotobi["provinsi"] == "Nusa Tenggara Timur"
    assert lewotobi["level"] == 3 and lewotobi["status"] == "Siaga"
    assert df[df["nama"] == "Agung"].iloc[0]["level"] == 1


def test_gabung_gempa_membuang_duplikat_lintas_sumber():
    usgs = sumber.parse_usgs(CONTOH_USGS)
    bmkg = usgs.copy()
    bmkg["sumber"] = "BMKG M5+"
    bmkg["waktu_utc"] = bmkg["waktu_utc"] + pd.Timedelta(seconds=20)
    bmkg["lat"] += 0.05
    bmkg["id"] = "bmkg-x"
    gabungan = sumber.gabung_gempa(usgs, bmkg)
    assert len(gabungan) == 1
    assert gabungan.iloc[0]["sumber"] == "USGS", "USGS diutamakan saat duplikat"


def test_gabung_gempa_mempertahankan_gempa_berbeda():
    usgs = sumber.parse_usgs(CONTOH_USGS)
    lain = usgs.copy()
    lain["lat"] -= 3
    lain["id"] = "lain"
    assert len(sumber.gabung_gempa(usgs, lain)) == 2


def test_gunung_api_statis_valid():
    df = sumber.muat_gunung_api_statis()
    assert len(df) == 69
    assert df["nama"].is_unique
    assert df["lat"].between(-11, 6).all() and df["lon"].between(95, 141).all()
    assert (df["elevasi_m"] >= 0).all()


def test_gabung_gunung_api_menempelkan_level():
    statis = sumber.muat_gunung_api_statis()
    level = pd.DataFrame({"nama": ["Lewotobi Laki-laki", "Semeru"], "provinsi": ["NTT", "Jatim"], "level": [3, 2], "status": ["Siaga", "Waspada"], "url_laporan": ["a", "b"]})
    df = sumber.gabung_gunung_api(statis, level)
    assert df.set_index("nama").loc["Lewotobi Laki-laki", "level"] == 3
    assert df.set_index("nama").loc["Semeru", "status"] == "Waspada"
    assert df.set_index("nama").loc["Agung", "level"] == 1
    assert len(df) == 69


def test_data_contoh_dapat_dimuat():
    gempa, gunung, meta = sumber.muat_sample()
    assert len(gempa) > 50
    assert gempa["magnitudo"].between(0, 10).all()
    assert set(gempa["sumber"]) <= {"USGS", "BMKG M5+", "BMKG dirasakan"}
    assert gunung["level"].between(1, 4).all()
    assert "diambil" in meta


def test_muat_semua_paksa_offline_tidak_menyentuh_jaringan(monkeypatch):
    def meledak(*a, **k):
        raise AssertionError("tidak boleh memanggil jaringan")

    monkeypatch.setattr(sumber.requests, "get", meledak)
    hasil = sumber.muat_semua(paksa_offline=True)
    assert hasil.offline is True
    assert not hasil.gempa.empty


def test_muat_semua_jatuh_ke_data_contoh_saat_jaringan_gagal(monkeypatch):
    def gagal(*a, **k):
        raise sumber.requests.ConnectionError("tidak ada internet")

    monkeypatch.setattr(sumber.requests, "get", gagal)
    hasil = sumber.muat_semua()
    assert hasil.offline is True
    assert len(hasil.kesalahan) == 4
    assert not hasil.gempa.empty and not hasil.gunung_api.empty


def test_parse_usgs_magtype_null_tidak_tertulis_none():
    geo = {"features": [{
        "id": "us1", "properties": {"mag": 4.0, "time": 1793452208987, "magType": None, "status": "automatic", "place": None},
        "geometry": {"coordinates": [128.9, -6.4, 10.0]},
    }]}
    r = sumber.parse_usgs(geo).iloc[0]
    assert r["keterangan"] == "automatic"
    assert r["wilayah"] == ""


def test_gabung_gempa_duplikat_di_batas_jendela_dua_menit():
    usgs = sumber.parse_usgs(CONTOH_USGS).head(1).copy()
    usgs["waktu_utc"] = pd.Timestamp("2026-01-01 01:59:59", tz="UTC")
    bmkg = usgs.copy()
    bmkg["sumber"] = "BMKG M5+"
    bmkg["id"] = "bmkg-x"
    bmkg["waktu_utc"] = pd.Timestamp("2026-01-01 02:00:01", tz="UTC")
    gabungan = sumber.gabung_gempa(usgs, bmkg)
    assert list(gabungan["sumber"]) == ["USGS"]


def test_gabung_gempa_tidak_membuang_gempa_susulan_dari_sumber_sama():
    usgs = sumber.parse_usgs(CONTOH_USGS).head(1).copy()
    usgs["waktu_utc"] = pd.Timestamp("2026-01-01 02:00:10", tz="UTC")
    susulan = usgs.copy()
    susulan["id"] = "susulan"
    susulan["waktu_utc"] = pd.Timestamp("2026-01-01 02:00:40", tz="UTC")
    assert len(sumber.gabung_gempa(pd.concat([usgs, susulan], ignore_index=True))) == 2


def test_gabung_gempa_selisih_sepuluh_menit_bukan_duplikat():
    usgs = sumber.parse_usgs(CONTOH_USGS).head(1).copy()
    bmkg = usgs.copy()
    bmkg["sumber"] = "BMKG M5+"
    bmkg["id"] = "bmkg-x"
    bmkg["waktu_utc"] = bmkg["waktu_utc"] + pd.Timedelta(minutes=10)
    assert len(sumber.gabung_gempa(usgs, bmkg)) == 2


def test_parse_usgs_geometri_null_dan_kedalaman_null():
    geo = {
        "features": [
            {"id": "a", "properties": {"mag": 4.5, "time": 1700000000000}, "geometry": None},
            {"id": "b", "properties": None, "geometry": {"coordinates": [120.0, -5.0, 10.0]}},
            {"id": "c", "properties": {"mag": 5.0, "time": 1700000000000}, "geometry": {"coordinates": [121.0, -6.0, None]}},
        ]
    }
    df = sumber.parse_usgs(geo)
    assert list(df["id"]) == ["c"]
    assert pd.isna(df.loc[0, "kedalaman_km"])
