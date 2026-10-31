"""Grafik Plotly untuk tab Pola. Setiap fungsi mengembalikan ``go.Figure``."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src import analisis

WARNA_KEDALAMAN = {
    "Dangkal (<70 km)": "#ff5a36",
    "Menengah (70–300 km)": "#ffb830",
    "Dalam (>300 km)": "#4fc3f7",
    "Tidak diketahui": "#9e9e9e",
}
WARNA_LEVEL = {1: "#7bd88f", 2: "#ffd23f", 3: "#ff8c42", 4: "#ff3b3b"}
WARNA_UTAMA = "#ff5a36"
WARNA_KEDUA = "#4fc3f7"


def _rapikan(fig: go.Figure, tinggi: int = 360) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=tinggi,
        margin=dict(l=10, r=10, t=50, b=10),
        title=dict(y=0.97, x=0, xanchor="left"),
        legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="left", x=0, title_text=""),
        font=dict(family="Inter, Segoe UI, sans-serif"),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)")
    return fig


def histogram_magnitudo(df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        df,
        x="magnitudo",
        color="kelas_kedalaman",
        color_discrete_map=WARNA_KEDALAMAN,
        category_orders={"kelas_kedalaman": analisis.URUTAN_KEDALAMAN},
        nbins=30,
        title="Sebaran magnitudo",
        labels={"magnitudo": "Magnitudo", "kelas_kedalaman": "Kedalaman"},
    )
    fig.update_layout(bargap=0.05, yaxis_title="Jumlah gempa")
    return _rapikan(fig)


def grafik_gutenberg_richter(mag: pd.Series) -> go.Figure:
    gr = analisis.gutenberg_richter(mag)
    hasil = analisis.b_value(mag)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=gr["magnitudo"], y=gr["log10_n"], mode="markers", name="Data (N ≥ M)", marker=dict(color=WARNA_KEDUA, size=8))
    )
    if not np.isnan(hasil["b"]):
        x = np.array([hasil["mc"], float(gr["magnitudo"].max())])
        y = hasil["a"] - hasil["b"] * x
        fig.add_trace(
            go.Scatter(x=x, y=y, mode="lines", name=f"log N = {hasil['a']:.2f} − {hasil['b']:.2f}·M", line=dict(color=WARNA_UTAMA, width=3))
        )
        fig.add_vline(x=hasil["mc"], line_dash="dot", line_color="#bbbbbb", annotation_text=f"Mc ≈ {hasil['mc']:.1f}", annotation_position="top right")
    fig.update_layout(title="Hukum Gutenberg–Richter", xaxis_title="Magnitudo M", yaxis_title="log₁₀ jumlah gempa ≥ M")
    return _rapikan(fig)


def sebaran_kedalaman(df: pd.DataFrame) -> go.Figure:
    fig = px.scatter(
        df,
        x="magnitudo",
        y="kedalaman_km",
        color="kelas_kedalaman",
        color_discrete_map=WARNA_KEDALAMAN,
        category_orders={"kelas_kedalaman": analisis.URUTAN_KEDALAMAN},
        hover_data={"wilayah": True, "waktu_wib": "|%d %b %H:%M", "sumber": True, "kelas_kedalaman": False},
        title="Magnitudo vs kedalaman",
        labels={"magnitudo": "Magnitudo", "kedalaman_km": "Kedalaman (km)", "kelas_kedalaman": "Kedalaman"},
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_traces(marker=dict(size=8, opacity=0.75, line=dict(width=0)))
    return _rapikan(fig)


def penampang_subduksi(df: pd.DataFrame, lon_min: float | None = None, lon_max: float | None = None) -> go.Figure:
    """Penampang bujur vs kedalaman: lempeng yang menunjam terlihat sebagai
    pita gempa yang semakin dalam ke arah tertentu (zona Wadati–Benioff)."""
    d = df
    if lon_min is not None and lon_max is not None:
        d = df[(df["lon"] >= lon_min) & (df["lon"] <= lon_max)]
    fig = px.scatter(
        d,
        x="lon",
        y="kedalaman_km",
        size="magnitudo",
        size_max=16,
        color="magnitudo",
        color_continuous_scale=["#4fc3f7", "#ffb830", "#ff5a36"],
        hover_data={"wilayah": True, "lat": ":.2f", "lon": ":.2f", "kedalaman_km": ":.0f"},
        title="Penampang bujur × kedalaman",
        labels={"lon": "Bujur (°)", "kedalaman_km": "Kedalaman (km)", "magnitudo": "M"},
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(coloraxis_colorbar=dict(title="M", thickness=10))
    return _rapikan(fig, 400)


def garis_waktu_harian(df: pd.DataFrame) -> go.Figure:
    h = analisis.per_hari(df)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=h["tanggal"], y=h["jumlah"], name="Jumlah gempa", marker_color=WARNA_KEDUA, opacity=0.85))
    fig.add_trace(
        go.Scatter(x=h["tanggal"], y=h["m_maks"], name="M maksimum", yaxis="y2", mode="lines+markers", line=dict(color=WARNA_UTAMA, width=2))
    )
    fig.update_layout(
        title="Gempa per hari (WIB)",
        yaxis=dict(title="Jumlah"),
        yaxis2=dict(title="M maks", overlaying="y", side="right", showgrid=False, range=[0, max(8, float(h["m_maks"].max() or 0) + 0.5)]),
        bargap=0.2,
    )
    return _rapikan(fig)


def grafik_per_jam(df: pd.DataFrame) -> go.Figure:
    j = analisis.per_jam(df)
    rata = j["jumlah"].mean() if not j.empty else 0
    fig = go.Figure(go.Bar(x=[f"{h:02d}" for h in j["jam"]], y=j["jumlah"], marker_color=WARNA_UTAMA, name="Jumlah"))
    fig.add_hline(y=rata, line_dash="dot", line_color="#bbbbbb", annotation_text=f"rata-rata {rata:.1f}", annotation_position="top left")
    fig.update_layout(title="Gempa menurut jam kejadian (WIB)", xaxis_title="Jam", yaxis_title="Jumlah", bargap=0.15)
    return _rapikan(fig, 320)


def grafik_energi(df: pd.DataFrame) -> go.Figure:
    e = analisis.energi_kumulatif(df)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=e["waktu_utc"],
            y=e["kumulatif_hiroshima"],
            mode="lines",
            line=dict(color=WARNA_UTAMA, width=3, shape="hv"),
            fill="tozeroy",
            fillcolor="rgba(255,90,54,0.15)",
            name="Energi kumulatif",
            hovertemplate="%{x|%d %b %H:%M}<br>%{y:.2f} × Hiroshima<extra></extra>",
        )
    )
    besar = e[e["magnitudo"] >= e["magnitudo"].quantile(0.97)] if not e.empty else e
    fig.add_trace(
        go.Scatter(
            x=besar["waktu_utc"],
            y=besar["kumulatif_hiroshima"],
            mode="markers+text",
            text=[f"M{m:.1f}" for m in besar["magnitudo"]],
            textposition="top center",
            marker=dict(color="#ffffff", size=8),
            name="Gempa terbesar",
            hoverinfo="skip",
        )
    )
    fig.update_layout(title="Energi yang dilepaskan (setara bom Hiroshima, kumulatif)", xaxis_title="Waktu (UTC)", yaxis_title="× Hiroshima")
    return _rapikan(fig)


def grafik_jeda(df: pd.DataFrame) -> go.Figure:
    jeda = analisis.jeda_antar_gempa(df)
    fig = px.histogram(x=jeda, nbins=40, title="Jeda antar gempa (menit)", labels={"x": "Menit", "y": "Jumlah"}, color_discrete_sequence=[WARNA_KEDUA])
    if not jeda.empty:
        fig.add_vline(x=float(jeda.median()), line_dash="dot", line_color="#ffffff", annotation_text=f"median {jeda.median():.0f} mnt", annotation_position="top right")
    fig.update_layout(yaxis_title="Jumlah", bargap=0.05)
    return _rapikan(fig, 320)


def grafik_level_gunung(gunung: pd.DataFrame) -> go.Figure:
    hitung = gunung["level"].value_counts().reindex([1, 2, 3, 4], fill_value=0)
    label = [f"Level {lvl} · {analisis_label(lvl)}" for lvl in hitung.index]
    fig = go.Figure(go.Bar(x=label, y=hitung.values, marker_color=[WARNA_LEVEL[l] for l in hitung.index], text=hitung.values, textposition="outside"))
    fig.update_layout(title="Tingkat aktivitas gunung api (MAGMA Indonesia)", yaxis_title="Jumlah gunung api")
    return _rapikan(fig, 320)


def analisis_label(level: int) -> str:
    from src.sumber import LEVEL_NAMA

    return LEVEL_NAMA.get(int(level), "?")


def grafik_zona(zona: pd.DataFrame) -> go.Figure:
    if zona.empty:
        return _rapikan(go.Figure())
    z = zona.iloc[::-1]
    nama = [f"{lab[:38]}…" if len(lab) > 38 else lab for lab in z["label"]]
    fig = go.Figure(
        go.Bar(
            x=z["jumlah"],
            y=nama,
            orientation="h",
            marker_color=WARNA_UTAMA,
            text=[f"M maks {m:.1f} · {k:.0f} km" for m, k in zip(z["m_maks"], z["kedalaman_median"])],
            textposition="inside",
            insidetextanchor="start",
        )
    )
    fig.update_layout(title="Zona paling ramai (kotak 2°×2°)", xaxis_title="Jumlah gempa", yaxis_title="")
    return _rapikan(fig, 360)
