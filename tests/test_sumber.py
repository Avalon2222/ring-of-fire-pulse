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
