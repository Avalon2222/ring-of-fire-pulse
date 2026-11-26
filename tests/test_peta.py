"""Tes popup dan tooltip peta: teks dari sumber luar tidak boleh jadi HTML."""

import pandas as pd

from src import peta


def _gempa(**ubah) -> pd.DataFrame:
    baris = {
        "id": "g1", "waktu_utc": pd.Timestamp("2026-11-01", tz="UTC"), "lat": -7.0, "lon": 110.0,
        "magnitudo": 5.1, "kedalaman_km": 10.0, "wilayah": "<script>x</script>", "sumber": "BMKG",
        "keterangan": "Dirasakan <b>III</b>", "url": "", "kelas_kedalaman": "Dangkal (<70 km)",
    }
    baris.update(ubah)
    return pd.DataFrame([baris])


def _gunung() -> pd.DataFrame:
    return pd.DataFrame([{
        "nama": "<i>Merapi</i>", "provinsi": "Jawa Tengah", "lat": -7.54, "lon": 110.44,
        "elevasi_m": 2930, "level": 3, "status": "Siaga", "url_laporan": "",
    }])


def test_teks_sumber_luar_di_escape():
    teks = peta.buat_peta(_gempa(), _gunung()).get_root().render()
    assert "<script>x</script>" not in teks
    assert "<i>Merapi</i>" not in teks
    assert "Dirasakan <b>III</b>" not in teks
    assert "&lt;script&gt;" in teks


def test_kedalaman_kosong_tidak_tampil_nan():
    teks = peta.buat_peta(_gempa(kedalaman_km=float("nan"), wilayah="Laut Banda"), _gunung()).get_root().render()
    assert "nan km" not in teks
    assert "kedalaman ?" in teks


def test_gempa_dan_gunung_tanpa_koordinat_dilewati():
    gempa = pd.concat([_gempa(), _gempa(id="g2", lat=float("nan"), wilayah="Tanpa Lokasi")], ignore_index=True)
    gunung = pd.concat([_gunung(), _gunung().assign(nama="Hilang", lon=float("nan"))], ignore_index=True)
    teks = peta.buat_peta(gempa, gunung, tampil_heatmap=True).get_root().render()
    assert "Tanpa Lokasi" not in teks
    assert "Gunung Hilang" not in teks
    assert "&lt;script&gt;" in teks


def test_url_dan_keterangan_nan_tidak_jadi_tautan_kosong():
    gunung = _gunung().assign(url_laporan=float("nan"))
    teks = peta.buat_peta(_gempa(url=float("nan"), keterangan=float("nan")), gunung).get_root().render()
    assert "Detail sumber" not in teks
    assert "Laporan MAGMA" not in teks


def test_gunung_tanpa_elevasi_tetap_tampil():
    teks = peta.buat_peta(_gempa(), _gunung().assign(elevasi_m=float("nan"))).get_root().render()
    assert "elevasi ?" in teks


def test_gunung_tanpa_level_tetap_tampil():
    gunung = pd.concat([_gunung(), _gunung().assign(nama="Baru", level=float("nan"))], ignore_index=True)
    teks = peta.buat_peta(_gempa(), gunung).get_root().render()
    assert "Gunung Baru · Level ? (Siaga)" in teks


def test_magnitudo_kosong_tidak_tampil_nan():
    teks = peta.buat_peta(_gempa(magnitudo=float("nan"), wilayah="Laut Maluku"), _gunung()).get_root().render()
    assert "M nan" not in teks
    assert "M ? · 10 km · Laut Maluku" in teks


def test_label_angka_tak_hingga_jadi_tanda_tanya():
    assert peta._kedalaman(float("inf")) == "kedalaman ?"
    assert peta._mag(float("-inf")) == "M ?"
    assert peta._kedalaman(33.4) == "33 km"
    assert peta._mag(5.25) == "M 5.2"
