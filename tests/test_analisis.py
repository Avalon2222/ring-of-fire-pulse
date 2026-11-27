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


def test_persen_dangkal_mengabaikan_kedalaman_kosong():
    df = buat_gempa(4)
    df["kedalaman_km"] = [10.0, 400.0, np.nan, np.nan]
    r = analisis.ringkasan(df, sekarang=pd.Timestamp("2026-11-01", tz="UTC"))
    assert r["persen_dangkal"] == pytest.approx(50.0)
    df["kedalaman_km"] = np.nan
    assert math.isnan(analisis.ringkasan(df)["persen_dangkal"])


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


def test_gunung_terdekat_koordinat_kosong():
    gunung = sumber.muat_gunung_api_statis()
    gempa = pd.DataFrame({"lat": [np.nan, -7.55], "lon": [np.nan, 110.45], "magnitudo": [4.0, 4.0]})
    dekat = analisis.gunung_terdekat(gempa, gunung)
    assert pd.isna(dekat.iloc[0]["gunung_terdekat"])
    assert math.isnan(dekat.iloc[0]["jarak_gunung_km"])
    assert dekat.iloc[1]["gunung_terdekat"] == "Merapi"


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


def test_kelas_kedalaman_nilai_kosong_apa_pun():
    for kosong in (None, float("nan"), np.nan, pd.NA):
        assert analisis.kelas_kedalaman(kosong) == "Tidak diketahui"


def test_magnitudo_lengkap_mengabaikan_nan():
    mag = pd.Series([4.5, 4.5, 4.5, None, 5.0, float("nan")])
    assert analisis.magnitudo_lengkap(mag) == pytest.approx(4.5)
    assert math.isnan(analisis.magnitudo_lengkap(pd.Series([None, None], dtype=float)))


def test_gempa_sekitar_gunung_abaikan_magnitudo_kosong():
    gunung = sumber.gabung_gunung_api(sumber.muat_gunung_api_statis(), None)
    gempa = pd.DataFrame({"lat": [-7.55, -7.56], "lon": [110.45, 110.44], "magnitudo": [4.2, np.nan]})
    sekitar = analisis.gempa_sekitar_gunung(gempa, gunung, radius_km=50)
    merapi = sekitar[sekitar["nama"] == "Merapi"].iloc[0]
    assert merapi["jumlah_gempa"] == 2
    assert merapi["m_maks"] == 4.2


def test_energi_kumulatif_tidak_putus_di_magnitudo_kosong():
    df = pd.DataFrame({
        "waktu_utc": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-03"], utc=True),
        "magnitudo": [5.0, np.nan, 6.0],
    })
    hasil = analisis.energi_kumulatif(df)
    assert hasil["kumulatif_j"].notna().all()
    assert hasil["kumulatif_j"].iloc[1] == pytest.approx(analisis.energi_joule(5.0))
    assert hasil["kumulatif_j"].iloc[2] == pytest.approx(analisis.energi_joule(5.0) + analisis.energi_joule(6.0))


def test_gutenberg_richter_bin_selain_satu_desimal():
    gr = analisis.gutenberg_richter(pd.Series([4.0, 4.05, 4.1, 4.3]), lebar_bin=0.05)
    assert gr["magnitudo"].is_unique
    assert list(gr["magnitudo"][:3]) == pytest.approx([4.0, 4.05, 4.1])
    assert list(gr["jumlah_kumulatif"][:3]) == [4, 3, 2]
    kasar = analisis.gutenberg_richter(pd.Series([4.1, 4.6, 5.2]), lebar_bin=0.5)
    assert list(kasar["magnitudo"]) == pytest.approx([4.0, 4.5, 5.0])
    assert list(kasar["jumlah_kumulatif"]) == [3, 2, 1]


def test_tambah_kolom_waktu_tanpa_zona_dianggap_utc():
    df = pd.DataFrame({"waktu_utc": pd.to_datetime(["2026-01-01 20:00"]), "kedalaman_km": [10.0], "magnitudo": [5.0]})
    hasil = analisis.tambah_kolom(df)
    assert hasil["jam_wib"].iloc[0] == 3
    assert str(hasil["tanggal_wib"].iloc[0]) == "2026-01-02"


def test_ringkasan_dan_denyut_menerima_waktu_tanpa_zona():
    df = pd.DataFrame({
        "waktu_utc": pd.to_datetime(["2026-11-01 00:00", "2026-11-02 00:00"]),
        "magnitudo": [4.0, 5.0], "kedalaman_km": [10.0, 20.0],
    })
    sekarang = pd.Timestamp("2026-11-02 06:00", tz="UTC")
    r = analisis.ringkasan(df, sekarang=sekarang)
    assert r["menit_sejak_terbaru"] == 360
    assert r["rentang_hari"] == 1
    d = analisis.denyut(df, jam=24, sekarang=pd.Timestamp("2026-11-02 06:00"))
    assert d["terakhir"] == 1


def test_per_hari_semua_waktu_kosong_tidak_crash():
    df = pd.DataFrame({"waktu_utc": [pd.NaT, pd.NaT], "magnitudo": [4.0, 5.0], "kedalaman_km": [10.0, 20.0]})
    hasil = analisis.per_hari(df)
    assert hasil.empty
    assert list(hasil.columns) == ["tanggal", "jumlah", "m_maks"]


def test_ringkasan_tanpa_waktu_valid_tetap_punya_laju():
    df = pd.DataFrame({"waktu_utc": [pd.NaT], "magnitudo": [4.0], "kedalaman_km": [10.0]})
    hasil = analisis.ringkasan(df, sekarang=pd.Timestamp("2024-01-01", tz="UTC"))
    assert hasil["rentang_hari"] == pytest.approx(1 / 24)
    assert hasil["per_hari"] == pytest.approx(24.0)


def test_zona_aktif_batas_negatif_dan_jumlah_seri():
    # 60 kotak berbeda dengan jumlah gempa 1-3 berselang-seling.
    baris = []
    for i in range(60):
        for _ in range(i % 3 + 1):
            baris.append({"lat": -10 + (i // 10) * 2.5, "lon": 95 + (i % 10) * 2.5, "magnitudo": 4.0,
                          "kedalaman_km": 10.0, "wilayah": "X"})
    df = pd.DataFrame(baris)
    assert analisis.zona_aktif(df, teratas=-3).empty
    z = analisis.zona_aktif(df, ukuran_derajat=2.0, teratas=20)
    assert (z["jumlah"] == 3).all()
    assert list(zip(z["lat"], z["lon"])) == sorted(zip(z["lat"], z["lon"]))


@pytest.mark.parametrize("ukuran", [0, -2.0, float("nan")])
def test_ukuran_kotak_dan_lebar_bin_harus_positif(ukuran):
    df = buat_gempa(20)
    with pytest.raises(ValueError):
        analisis.zona_aktif(df, ukuran_derajat=ukuran)
    with pytest.raises(ValueError):
        analisis.magnitudo_lengkap(df["magnitudo"], lebar_bin=ukuran)
    with pytest.raises(ValueError):
        analisis.gutenberg_richter(df["magnitudo"], lebar_bin=ukuran)


def test_denyut_waktu_kosong_tidak_menghasilkan_nan():
    sekarang = pd.Timestamp("2026-11-01", tz="UTC")
    semua_kosong = pd.DataFrame({"waktu_utc": [None, None], "magnitudo": [4.0, 5.0]})
    assert analisis.denyut(semua_kosong, 24, sekarang) == {"terakhir": 0, "rata_rata": 0.0, "rasio": 0.0}
    sebagian = pd.DataFrame({"waktu_utc": ["2026-10-31 12:00", None], "magnitudo": [4.0, 5.0]})
    hasil = analisis.denyut(sebagian, 24, sekarang)
    assert hasil["terakhir"] == 1
    assert hasil["rata_rata"] == pytest.approx(1.0)


def test_b_value_dengan_mc_tetap_cek_lebar_bin():
    with pytest.raises(ValueError, match="lebar_bin"):
        analisis.b_value(pd.Series([4.0, 4.0, 4.0]), mc=4.0, lebar_bin=0)
    with pytest.raises(ValueError, match="lebar_bin"):
        analisis.b_value(pd.Series([4.0, 4.5]), mc=4.0, lebar_bin=-0.1)


def test_magnitudo_tak_hingga_diabaikan():
    mag = pd.Series([4.0, 4.0, 4.5, np.inf, -np.inf, np.nan])
    assert analisis.magnitudo_lengkap(mag) == pytest.approx(4.0)
    gr = analisis.gutenberg_richter(mag)
    assert gr["magnitudo"].max() == pytest.approx(4.5)
    assert gr["jumlah_kumulatif"].iloc[0] == 3


def test_b_value_mengabaikan_magnitudo_inf():
    df = buat_gempa(500)
    bersih = analisis.b_value(df["magnitudo"], mc=3.0)
    kotor = analisis.b_value(pd.concat([df["magnitudo"], pd.Series([np.inf])], ignore_index=True), mc=3.0)
    assert kotor["n"] == bersih["n"]
    assert kotor["b"] == pytest.approx(bersih["b"])


def test_energi_kumulatif_magnitudo_inf_dihitung_nol():
    df = pd.DataFrame({
        "waktu_utc": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-03"], utc=True),
        "magnitudo": [5.0, np.inf, 6.0],
    })
    hasil = analisis.energi_kumulatif(df)
    assert np.isfinite(hasil["kumulatif_j"]).all()
    assert hasil["kumulatif_j"].iloc[2] == pytest.approx(analisis.energi_joule(5.0) + analisis.energi_joule(6.0))


def test_ringkasan_magnitudo_tak_hingga_diabaikan():
    df = pd.DataFrame({
        "waktu_utc": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 01:00"], utc=True),
        "magnitudo": [4.0, float("inf")],
        "kedalaman_km": [10.0, 20.0],
    })
    r = analisis.ringkasan(df, sekarang=pd.Timestamp("2024-01-02", tz="UTC"))
    assert r["m_maks"] == 4.0
    assert math.isfinite(r["energi_total_j"])
    assert r["energi_total_j"] == pytest.approx(analisis.energi_joule(4.0))


def test_jeda_antar_gempa_waktu_teks_dan_kosong():
    df = pd.DataFrame({"waktu_utc": ["2024-01-01T00:10:00Z", "2024-01-01T00:00:00Z", None, "2024-01-01T00:40:00Z"]})
    assert analisis.jeda_antar_gempa(df).tolist() == [10.0, 30.0]


def test_jeda_antar_gempa_format_waktu_campuran():
    df = pd.DataFrame({
        "waktu_utc": ["2026-01-01T09:00:00", "2026-01-01 10:00:00", "2026-01-01T18:30:00+07:00"],
        "magnitudo": [5.0, 4.0, 4.5],
    })
    # 18:30 WIB = 11:30 UTC, jadi jedanya 60 dan 90 menit; dulu dua baris terakhir jadi NaT.
    assert analisis.jeda_antar_gempa(df).tolist() == [60.0, 90.0]


def test_tambah_kolom_format_waktu_campuran():
    df = pd.DataFrame({
        "waktu_utc": ["2026-01-01T09:00:00", "2026-01-01 10:00:00"],
        "magnitudo": [5.0, 4.0], "kedalaman_km": [10.0, 80.0],
    })
    hasil = analisis.tambah_kolom(df)
    assert hasil["jam_wib"].tolist() == [16, 17]
