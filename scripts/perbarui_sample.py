"""Unduh ulang data contoh ke ``data/sample``.

Dipakai agar aplikasi tetap berjalan tanpa internet dan agar pengujian
tidak bergantung pada jaringan. Jalankan dari akar proyek:

    python scripts/perbarui_sample.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))

from src import sumber  # noqa: E402

DIR = sumber.DIR_SAMPLE
DIR.mkdir(parents=True, exist_ok=True)


def simpan_json(nama: str, isi: dict) -> None:
    (DIR / nama).write_text(json.dumps(isi, ensure_ascii=False), encoding="utf-8")
    print(f"  {nama}: {(DIR / nama).stat().st_size // 1024} KB")


def utama(hari: int = 30, magnitudo_min: float = 2.5) -> None:
    print("Mengunduh data contoh ...")
    simpan_json("bmkg_terkini.json", sumber._get_json(sumber.URL_BMKG_TERKINI))
    simpan_json("bmkg_dirasakan.json", sumber._get_json(sumber.URL_BMKG_DIRASAKAN))

    mulai = datetime.now(timezone.utc)
    params = {
        "format": "geojson",
        "starttime": (mulai - timedelta(days=hari)).strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": magnitudo_min,
        "orderby": "time",
        "limit": 20000,
        **sumber.KOTAK_INDONESIA,
    }
    usgs = sumber._get_json(sumber.URL_USGS, params)
    # Buang kolom yang tidak dipakai agar berkas tetap ringkas.
    for f in usgs.get("features", []):
        p = f["properties"]
        f["properties"] = {k: p.get(k) for k in ("mag", "place", "time", "url", "magType", "status", "tsunami", "type")}
    simpan_json("usgs.json", usgs)

    r = requests.get(sumber.URL_MAGMA, timeout=sumber.TIMEOUT, headers=sumber.HEADERS)
    r.raise_for_status()
    level = sumber.parse_magma(r.text)
    level.to_csv(DIR / "magma_level.csv", index=False)
    print(f"  magma_level.csv: {len(level)} gunung api")

    meta = {
        "diambil": mulai.strftime("%Y-%m-%d %H:%M UTC"),
        "hari": hari,
        "magnitudo_min": magnitudo_min,
        "jumlah_usgs": len(usgs.get("features", [])),
        "catatan": "Data contoh untuk mode offline dan pengujian. Perbarui dengan scripts/perbarui_sample.py.",
    }
    simpan_json("meta.json", meta)
    print("Selesai.")


if __name__ == "__main__":
    utama()
