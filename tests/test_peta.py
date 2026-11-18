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
