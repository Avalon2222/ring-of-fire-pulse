"""Pengujian fungsi analisis dengan data buatan yang hasilnya diketahui."""

import math

import numpy as np
import pandas as pd
import pytest

from src import analisis, sumber


def buat_gempa(n: int = 200, seed: int = 7) -> pd.DataFrame:
    """Katalog sintetis yang mengikuti Gutenberg-Richter dengan b = 1."""
    rng = np.random.default_rng(seed)
    mc = 3.0
    # b = 1 -> eksponensial berskala 1/ln(10); mulai dari Mc - 0,05 agar setelah
    # pembulatan ke 0,1 bin terendah tepat berpusat di Mc.
    mag = (mc - 0.05) + rng.exponential(scale=1 / math.log(10), size=n)
    waktu = pd.Timestamp("2026-10-01", tz="UTC") + pd.to_timedelta(np.sort(rng.uniform(0, 30 * 86400, n)), unit="s")
    return pd.DataFrame(
        {
            "id": [f"s{i}" for i in range(n)],
            "waktu_utc": waktu,
            "lat": rng.uniform(-10, 5, n),
            "lon": rng.uniform(95, 140, n),
            "magnitudo": np.round(mag, 1),
            "kedalaman_km": rng.choice([10.0, 50.0, 120.0, 400.0], n),
            "wilayah": rng.choice(["Laut Banda", "Selatan Jawa", "Barat Sumatra"], n),
            "sumber": "USGS",
            "keterangan": "",
            "url": "",
        }
    )


def test_kelas_kedalaman_batasnya_benar():
    assert analisis.kelas_kedalaman(10) == "Dangkal (<70 km)"
    assert analisis.kelas_kedalaman(69.9) == "Dangkal (<70 km)"
    assert analisis.kelas_kedalaman(70) == "Menengah (70–300 km)"
    assert analisis.kelas_kedalaman(300) == "Dalam (>300 km)"
    assert analisis.kelas_kedalaman(float("nan")) == "Tidak diketahui"


def test_energi_naik_32_kali_per_satu_magnitudo():
    rasio = analisis.energi_joule(6.0) / analisis.energi_joule(5.0)
    assert rasio == pytest.approx(10 ** 1.5, rel=1e-6)
    # Gempa M6 ~ 1 bom Hiroshima (orde yang sama)
    assert 0.5 < analisis.setara_hiroshima(analisis.energi_joule(6.0)) < 2


def test_tambah_kolom_konversi_ke_wib():
    df = analisis.tambah_kolom(buat_gempa(5))
    assert (df["waktu_wib"] - df["waktu_utc"].dt.tz_convert("Asia/Jakarta") == pd.Timedelta(0)).all()
    assert df["jam_wib"].between(0, 23).all()
    assert set(df["kelas_kedalaman"]) <= set(analisis.URUTAN_KEDALAMAN)


def test_b_value_mendekati_satu_untuk_data_sintetis():
    df = buat_gempa(3000)
    hasil = analisis.b_value(df["magnitudo"], mc=3.0)
    assert hasil["n"] == 3000
    assert hasil["b"] == pytest.approx(1.0, abs=0.08)
    assert hasil["galat"] < 0.05


def test_b_value_sedikit_data_mengembalikan_nan():
    hasil = analisis.b_value(pd.Series([4.0]))
    assert math.isnan(hasil["b"]) and hasil["n"] == 1


def test_gutenberg_richter_kumulatif_menurun():
    gr = analisis.gutenberg_richter(pd.Series([3.0, 3.0, 3.5, 4.0, 5.0]))
    assert gr["jumlah_kumulatif"].is_monotonic_decreasing
    assert gr.iloc[0]["jumlah_kumulatif"] == 5
    assert gr[gr["magnitudo"] == 5.0].iloc[0]["jumlah_kumulatif"] == 1


def test_ringkasan_dan_denyut():
    df = analisis.tambah_kolom(buat_gempa(100))
    sekarang = df["waktu_utc"].max() + pd.Timedelta(hours=1)
    r = analisis.ringkasan(df, sekarang)
    assert r["jumlah"] == 100
    assert r["m_maks"] == df["magnitudo"].max()
    assert r["menit_sejak_terbaru"] == pytest.approx(60)
    d = analisis.denyut(df, 24, sekarang)
    assert d["terakhir"] == int((df["waktu_utc"] >= sekarang - pd.Timedelta(hours=24)).sum())
    assert d["rata_rata"] > 0


def test_per_hari_mengisi_hari_kosong():
    df = pd.DataFrame(
        {
            "waktu_utc": pd.to_datetime(["2026-10-01T01:00", "2026-10-03T01:00"], utc=True),
            "magnitudo": [4.0, 5.0],
            "kedalaman_km": [10.0, 10.0],
        }
    )
    h = analisis.per_hari(df)
    assert len(h) == 3
    assert h["jumlah"].tolist() == [1, 0, 1]


def test_per_jam_selalu_24_baris():
    j = analisis.per_jam(buat_gempa(50))
    assert len(j) == 24 and j["jumlah"].sum() == 50


def test_jeda_dan_energi_kumulatif():
    df = buat_gempa(20)
    jeda = analisis.jeda_antar_gempa(df)
    assert len(jeda) == 19 and (jeda >= 0).all()
    e = analisis.energi_kumulatif(df)
    assert e["kumulatif_j"].is_monotonic_increasing
    assert e["kumulatif_j"].iloc[-1] == pytest.approx(df["magnitudo"].map(analisis.energi_joule).sum())


def test_haversine_jakarta_surabaya():
    jarak = analisis.haversine_km(-6.2088, 106.8456, -7.2575, 112.7521)
    assert 650 < float(jarak) < 680


def test_gunung_terdekat_dan_radius():
    gunung = sumber.muat_gunung_api_statis()
    gunung["level"] = 1
    gempa = pd.DataFrame(
        {
            "id": ["a", "b"],
            "waktu_utc": pd.to_datetime(["2026-10-01", "2026-10-02"], utc=True),
            "lat": [-7.55, -2.0],
            "lon": [110.45, 135.0],
            "magnitudo": [4.0, 5.0],
            "kedalaman_km": [10.0, 10.0],
            "wilayah": ["dekat Merapi", "Papua"],
            "sumber": "USGS",
            "keterangan": "",
            "url": "",
        }
    )
    dekat = analisis.gunung_terdekat(gempa, gunung)
    assert dekat.iloc[0]["gunung_terdekat"] == "Merapi"
    assert dekat.iloc[0]["jarak_gunung_km"] < 5
    sekitar = analisis.gempa_sekitar_gunung(gempa, gunung, radius_km=50)
    assert sekitar.iloc[0]["nama"] == "Merapi" and sekitar.iloc[0]["jumlah_gempa"] == 1
    assert sekitar["jumlah_gempa"].sum() >= 1
    assert sekitar[sekitar["nama"] == "Merapi"].iloc[0]["m_maks"] == 4.0


def test_zona_aktif_mengurutkan_dari_terbanyak():
    df = buat_gempa(300)
    z = analisis.zona_aktif(df, ukuran_derajat=2.0, teratas=5)
    assert len(z) == 5
    assert z["jumlah"].is_monotonic_decreasing
    assert z["jumlah"].sum() <= 300


def test_fungsi_tahan_bingkai_kosong():
    kosong = analisis.tambah_kolom(sumber._bingkai_kosong())
    assert analisis.ringkasan(kosong) == {"jumlah": 0}
    assert analisis.per_hari(kosong).empty
    assert analisis.jeda_antar_gempa(kosong).empty
    assert analisis.zona_aktif(kosong).empty
    assert analisis.energi_kumulatif(kosong).empty
