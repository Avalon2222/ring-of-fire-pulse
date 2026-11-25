"""Peta Folium: gempa (lingkaran berukuran magnitudo, warna kedalaman),
gunung api (segitiga berwarna level MAGMA), heatmap, dan garis palung."""

from __future__ import annotations

import html

import folium
import pandas as pd
from branca.element import MacroElement, Template
from folium.plugins import HeatMap

from src.grafik import WARNA_KEDALAMAN, WARNA_LEVEL
from src.sumber import LEVEL_NAMA

PUSAT_INDONESIA = (-2.5, 118.0)

# Perkiraan kasar jalur Palung Sunda-Jawa dan Palung Timor (bukan data resmi,
# hanya penanda visual agar pembaca tahu di mana lempeng Indo-Australia menunjam).
PALUNG_SUNDA = [
    (6.0, 92.5), (3.5, 93.8), (1.0, 95.8), (-1.5, 98.0), (-4.0, 100.2), (-6.0, 102.5),
    (-7.8, 105.0), (-9.6, 108.0), (-10.6, 111.0), (-11.0, 114.0), (-11.0, 117.5), (-10.8, 121.0),
]
PALUNG_TIMOR = [(-10.8, 121.0), (-10.4, 124.0), (-9.4, 127.0), (-8.0, 129.5), (-6.5, 131.0), (-5.0, 132.0)]


def radius_gempa(m: float) -> float:
    """Jari-jari piksel: tumbuh kuadratik agar M6 jelas lebih mencolok dari M4."""
    return max(3.0, (m ** 2) / 4.5)


def _teks(v) -> str:
    """Teks dari data luar (BMKG, USGS, MAGMA) di-escape sebelum masuk HTML."""
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else html.escape(str(v))


def _kedalaman(km) -> str:
    """Kedalaman BMKG kadang kosong; tampilkan tanda tanya, bukan "nan km"."""
    return "kedalaman ?" if km is None or pd.isna(km) else f"{km:.0f} km"


def _ada(v) -> bool:
    """True kalau nilai berisi teks; NaN dari CSV itu truthy, jadi `if r.get(...)` saja tidak cukup."""
    return v is not None and not (not isinstance(v, str) and pd.isna(v)) and str(v).strip() != ""


def _elevasi(m) -> str:
    try:
        return f"{int(m)} mdpl"
    except (TypeError, ValueError):  # NaN, pd.NA, atau None dari data MAGMA
        return "elevasi ?"


def _level(v) -> int | None:
    """Level MAGMA sebagai int; kosong/rusak jadi None (int(NaN) melempar ValueError)."""
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        return None


def _popup_gempa(r: pd.Series) -> str:
    waktu = r["waktu_wib"].strftime("%d %b %Y %H:%M WIB") if "waktu_wib" in r and pd.notna(r["waktu_wib"]) else ""
    tautan = f'<br><a href="{_teks(r["url"])}" target="_blank">Detail sumber</a>' if _ada(r.get("url")) else ""
    return (
        f"<b>M {r['magnitudo']:.1f}</b> · {_kedalaman(r['kedalaman_km'])}<br>{_teks(r['wilayah'])}<br>"
        f"<span style='color:#888'>{waktu} · {_teks(r['sumber'])}</span>"
        f"{('<br>' + _teks(r['keterangan'])) if _ada(r.get('keterangan')) else ''}{tautan}"
    )


def _popup_gunung(r: pd.Series) -> str:
    tautan = f'<br><a href="{_teks(r["url_laporan"])}" target="_blank">Laporan MAGMA</a>' if _ada(r.get("url_laporan")) else ""
    return (
        f"<b>Gunung {_teks(r['nama'])}</b><br>{_teks(r['provinsi'])} · {_elevasi(r['elevasi_m'])}<br>"
        f"Level {_teks(_level(r['level']) if _level(r['level']) is not None else '?')} · <b>{_teks(r['status'])}</b>{tautan}"
    )


def buat_peta(
    gempa: pd.DataFrame,
    gunung: pd.DataFrame,
    tampil_gempa: bool = True,
    tampil_gunung: bool = True,
    tampil_heatmap: bool = False,
    tampil_palung: bool = True,
    pusat: tuple[float, float] = PUSAT_INDONESIA,
    zoom: int = 5,
    sorot_id: str | None = None,
) -> folium.Map:
    m = folium.Map(location=pusat, zoom_start=zoom, tiles=None, control_scale=True, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        name="Gelap (Esri)",
        max_zoom=16,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics",
        name="Citra satelit (Esri)",
        show=False,
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)

    if tampil_palung:
        fg_palung = folium.FeatureGroup(name="Palung (perkiraan)", show=True)
        for jalur, nama in ((PALUNG_SUNDA, "Palung Sunda–Jawa"), (PALUNG_TIMOR, "Palung Timor")):
            folium.PolyLine(jalur, color="#9aa0ff", weight=2, opacity=0.5, dash_array="6 6", tooltip=f"{nama} (perkiraan)").add_to(fg_palung)
        fg_palung.add_to(m)

    # Folium menolak lokasi NaN ("Location values cannot contain NaNs"), jadi satu gempa
    # atau gunung tanpa koordinat akan menggagalkan seluruh peta. Lewati saja.
    gempa = gempa.dropna(subset=["lat", "lon"])
    gunung = gunung.dropna(subset=["lat", "lon"])

    if tampil_heatmap and not gempa.empty:
        fg_heat = folium.FeatureGroup(name="Heatmap", show=True)
        HeatMap(gempa[["lat", "lon", "magnitudo"]].values.tolist(), radius=22, blur=18, min_opacity=0.25).add_to(fg_heat)
        fg_heat.add_to(m)

    if tampil_gempa and not gempa.empty:
        fg_gempa = folium.FeatureGroup(name="Gempa", show=True)
        for _, r in gempa.sort_values("magnitudo").iterrows():
            disorot = sorot_id is not None and r["id"] == sorot_id
            folium.CircleMarker(
                location=(r["lat"], r["lon"]),
                radius=radius_gempa(r["magnitudo"]) * (1.6 if disorot else 1),
                color="#ffffff" if disorot else WARNA_KEDALAMAN.get(r.get("kelas_kedalaman", ""), "#9e9e9e"),
                weight=2 if disorot else 1,
                fill=True,
                fill_color=WARNA_KEDALAMAN.get(r.get("kelas_kedalaman", ""), "#9e9e9e"),
                fill_opacity=0.55,
                tooltip=f"M {r['magnitudo']:.1f} · {_kedalaman(r['kedalaman_km'])} · {_teks(r['wilayah'])}",
                popup=folium.Popup(_popup_gempa(r), max_width=280),
            ).add_to(fg_gempa)
        fg_gempa.add_to(m)

    if tampil_gunung and not gunung.empty:
        fg_gunung = folium.FeatureGroup(name="Gunung api", show=True)
        for _, r in gunung.sort_values("level").iterrows():
            level = _level(r["level"])
            warna = WARNA_LEVEL.get(level, "#9e9e9e")
            ukuran = 12 + 4 * (level or 0)
            ikon = folium.DivIcon(
                html=(
                    f'<div style="font-size:{ukuran}px;line-height:1;color:{warna};'
                    f'text-shadow:0 0 4px #000, 0 0 10px {warna if (level or 0) >= 3 else "transparent"};">&#9650;</div>'
                ),
                icon_size=(ukuran, ukuran),
                icon_anchor=(ukuran // 2, ukuran // 2),
            )
            folium.Marker(
                location=(r["lat"], r["lon"]),
                icon=ikon,
                tooltip=f"Gunung {_teks(r['nama'])} · Level {level if level is not None else '?'} ({_teks(r['status'])})",
                popup=folium.Popup(_popup_gunung(r), max_width=260),
            ).add_to(fg_gunung)
        fg_gunung.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    m.get_root().add_child(_legenda())
    return m


def _legenda() -> MacroElement:
    baris_kedalaman = "".join(
        f'<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{w};margin-right:6px"></span>{k}</div>'
        for k, w in WARNA_KEDALAMAN.items()
        if k != "Tidak diketahui"
    )
    baris_level = "".join(
        f'<div><span style="color:{w};margin-right:6px">&#9650;</span>Level {lvl} · {LEVEL_NAMA[lvl]}</div>' for lvl, w in WARNA_LEVEL.items()
    )
    html = f"""
    {{% macro html(this, kwargs) %}}
    <div style="position:fixed;bottom:24px;left:12px;z-index:9999;background:rgba(14,15,18,0.88);color:#eee;
                padding:10px 12px;border-radius:8px;font:12px/1.6 Inter,Segoe UI,sans-serif;border:1px solid #333">
      <div style="font-weight:600;margin-bottom:2px">Gempa · ukuran = magnitudo</div>{baris_kedalaman}
      <div style="font-weight:600;margin:6px 0 2px">Gunung api · status MAGMA</div>{baris_level}
    </div>
    {{% endmacro %}}
    """
    macro = MacroElement()
    macro._template = Template(html)
    return macro
