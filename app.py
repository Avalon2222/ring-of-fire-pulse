"""The Pulse of the Ring of Fire — denyut gempa dan gunung api Indonesia.

Jalankan: ``streamlit run app.py``
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src import analisis, grafik, peta, sumber

st.set_page_config(page_title="The Pulse of the Ring of Fire", page_icon="🌋", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    .blok-judul h1 {margin-bottom:0; font-size:2.3rem; letter-spacing:-0.02em}
    .blok-judul .tagline {color:#ff5a36; font-size:1.05rem; font-weight:600; margin:0 0 .3rem}
    .blok-judul .sub {color:#a9a79f; margin:0}
    div[data-testid="stMetricValue"] {font-size:1.6rem}
    .catatan {color:#a9a79f; font-size:.85rem}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Mengambil data BMKG, USGS, dan MAGMA ...")
def muat(hari: int, magnitudo_min: float, offline: bool) -> sumber.HasilMuat:
    return sumber.muat_semua(hari=hari, magnitudo_min=magnitudo_min, paksa_offline=offline)


def format_menit(menit: float) -> str:
    if menit < 60:
        return f"{menit:.0f} menit lalu"
    if menit < 48 * 60:
        return f"{menit / 60:.1f} jam lalu"
    return f"{menit / 1440:.1f} hari lalu"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Pengaturan")
    mode = st.radio("Sumber data", ["Langsung (BMKG + USGS + MAGMA)", "Offline (data contoh)"], index=0)
    offline = mode.startswith("Offline")
    hari = st.select_slider("Jendela katalog USGS", options=[7, 14, 30], value=30, format_func=lambda h: f"{h} hari")
    mag_min = st.slider("Magnitudo minimum", 2.5, 6.0, 2.5, 0.1)
    kelas = st.multiselect("Kelas kedalaman", analisis.URUTAN_KEDALAMAN, default=analisis.URUTAN_KEDALAMAN)
    st.markdown("### 🗺️ Lapisan peta")
    tampil_gempa = st.checkbox("Gempa", True)
    tampil_gunung = st.checkbox("Gunung api", True)
    tampil_heatmap = st.checkbox("Heatmap gempa", False)
    tampil_palung = st.checkbox("Garis palung (perkiraan)", True)
    if st.button("🔄 Muat ulang data", width="stretch"):
        muat.clear()
        st.rerun()
    st.markdown(
        '<p class="catatan">Data diperbarui otomatis tiap 10 menit. Jika jaringan gagal, aplikasi memakai data contoh.</p>',
        unsafe_allow_html=True,
    )

hasil = muat(hari, 2.5, offline)
gempa_semua = analisis.tambah_kolom(hasil.gempa)
gunung = hasil.gunung_api
gempa = gempa_semua[(gempa_semua["magnitudo"] >= mag_min) & (gempa_semua["kelas_kedalaman"].isin(kelas))].reset_index(drop=True)
sekarang = pd.Timestamp.now(tz="UTC")


# ---------------------------------------------------------------------------
# Judul dan status
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="blok-judul">
      <h1>🌋 The Pulse of the Ring of Fire</h1>
      <p class="tagline">The ground never sleeps.</p>
      <p class="sub">Peta langsung gempa dan gunung api Indonesia dari BMKG, USGS, dan MAGMA Indonesia, beserta pola magnitudo, kedalaman, dan waktunya.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if hasil.offline:
    rincian = "; ".join(hasil.kesalahan) if hasil.kesalahan else "mode offline dipilih"
    st.warning(f"Sebagian atau seluruh data berasal dari **data contoh** ({sumber.muat_sample()[2]['diambil']}). {rincian}", icon="📦")
else:
    waktu = hasil.waktu_ambil.astimezone(timezone.utc).strftime("%d %b %Y %H:%M UTC") if hasil.waktu_ambil else "-"
    st.caption(f"Data langsung · diambil {waktu} · {', '.join(f'{k}: {v}' for k, v in hasil.sumber_gempa.items())} · MAGMA: {hasil.sumber_gunung}")

if gempa.empty:
    st.error("Tidak ada gempa yang lolos filter. Turunkan magnitudo minimum atau tambah kelas kedalaman.")
    st.stop()

ring = analisis.ringkasan(gempa, sekarang)
dny = analisis.denyut(gempa, 24, sekarang)
siaga = gunung[gunung["level"] >= 3]

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Gempa tercatat", f"{ring['jumlah']:,}", f"{ring['per_hari']:.1f} per hari", delta_color="off")
k2.metric("Gempa terakhir", f"M {ring['terbaru']['magnitudo']:.1f}", format_menit(ring["menit_sejak_terbaru"]), delta_color="off")
k3.metric("Terbesar", f"M {ring['m_maks']:.1f}", f"{ring['terbesar']['kedalaman_km']:.0f} km", delta_color="off")
k4.metric("Denyut 24 jam", f"{dny['terakhir']} gempa", f"{dny['rasio']:.1f}× laju harian", delta_color="off")
k5.metric("Gunung Siaga/Awas", f"{len(siaga)}", ", ".join(siaga["nama"].head(3)) if not siaga.empty else "tidak ada", delta_color="off")
k6.metric("Energi (× bom Hiroshima)", f"{ring['energi_hiroshima']:.1f}×", f"M median {ring['m_median']:.1f}", delta_color="off")

tab_peta, tab_pola, tab_gunung, tab_data, tab_cara = st.tabs(["🗺️ Peta", "📈 Pola", "🌋 Gunung Api", "📋 Data & Sumber", "🧭 Cara Kerja"])


# ---------------------------------------------------------------------------
# Tab Peta
# ---------------------------------------------------------------------------

with tab_peta:
    kolom_peta, kolom_daftar = st.columns([3, 1.15])
    with kolom_daftar:
        st.markdown("#### Terbaru")
        terbaru = gempa.sort_values("waktu_utc", ascending=False).head(12)
        pilihan = st.selectbox(
            "Sorot gempa di peta",
            options=["(tidak ada)"] + terbaru["id"].tolist(),
            format_func=lambda i: "(tidak ada)" if i == "(tidak ada)" else f"M {terbaru.set_index('id').loc[i, 'magnitudo']:.1f} · {terbaru.set_index('id').loc[i, 'wilayah'][:34]}",
        )
        for _, r in terbaru.iterrows():
            warna = grafik.WARNA_KEDALAMAN.get(r["kelas_kedalaman"], "#999")
            st.markdown(
                f"<div style='border-left:3px solid {warna};padding:2px 8px;margin:4px 0'>"
                f"<b>M {r['magnitudo']:.1f}</b> · {r['kedalaman_km']:.0f} km<br>"
                f"<span style='font-size:.85rem'>{r['wilayah']}</span><br>"
                f"<span class='catatan'>{r['waktu_wib'].strftime('%d %b %H:%M')} WIB · {r['sumber']}</span></div>",
                unsafe_allow_html=True,
            )
    with kolom_peta:
        sorot = None if pilihan == "(tidak ada)" else pilihan
        if sorot is not None:
            baris = gempa.set_index("id").loc[sorot]
            pusat, zoom = (float(baris["lat"]), float(baris["lon"])), 7
        else:
            pusat, zoom = peta.PUSAT_INDONESIA, 5
        m = peta.buat_peta(gempa, gunung, tampil_gempa, tampil_gunung, tampil_heatmap, tampil_palung, pusat=pusat, zoom=zoom, sorot_id=sorot)
        st_folium(m, height=620, use_container_width=True, returned_objects=[])
        st.markdown(
            '<p class="catatan">Lingkaran: gempa, ukuran mengikuti magnitudo, warna mengikuti kedalaman. Segitiga: gunung api, warna mengikuti level MAGMA. '
            "Klik objek untuk rincian dan tautan ke sumber.</p>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Tab Pola
# ---------------------------------------------------------------------------

with tab_pola:
    st.markdown("#### Magnitudo")
    c1, c2 = st.columns(2)
    c1.plotly_chart(grafik.histogram_magnitudo(gempa), width="stretch")
    c2.plotly_chart(grafik.grafik_gutenberg_richter(gempa["magnitudo"]), width="stretch")
    bv = analisis.b_value(gempa["magnitudo"])
    if not pd.isna(bv["b"]):
        b1, b2, b3 = st.columns(3)
        b1.metric("b-value", f"{bv['b']:.2f} ± {bv['galat']:.2f}", "≈ 1 normal untuk zona subduksi", delta_color="off")
        b2.metric("Magnitudo kelengkapan (Mc)", f"{bv['mc']:.1f}", f"{bv['n']} gempa di atas Mc", delta_color="off")
        b3.metric("Perkiraan: 1 gempa M6+ setiap", f"{10 ** (bv['b'] * 6 - bv['a']) * ring['rentang_hari']:.0f} hari", "dari garis Gutenberg–Richter", delta_color="off")
    with st.expander("Apa itu hukum Gutenberg–Richter dan b-value?"):
        st.markdown(
            """
            Jumlah gempa dengan magnitudo **≥ M** turun secara eksponensial terhadap M: `log10 N = a − b·M`.
            Setiap kenaikan satu magnitudo, jumlah gempa berkurang sekitar sepuluh kali lipat bila `b ≈ 1`.
            `b` ditaksir dengan rumus Aki (1965): `b = log10(e) / (M̄ − (Mc − 0,05))`, hanya memakai gempa di atas
            **magnitudo kelengkapan (Mc)**, yaitu ambang di bawahnya jaringan seismometer mulai "kelewatan" mencatat gempa kecil.
            `b` jauh di bawah 1 berarti proporsi gempa besar lebih tinggi dari biasanya; `b` di atas 1,3 sering muncul pada kawanan gempa vulkanik.
            Dengan jendela hanya beberapa pekan dan ratusan gempa, angka ini kasar, tetapi cukup untuk melihat bentuk hukumnya.
            """
        )

    st.markdown("#### Kedalaman")
    c3, c4 = st.columns(2)
    c3.plotly_chart(grafik.sebaran_kedalaman(gempa), width="stretch")
    with c4:
        lon_rentang = st.slider("Rentang bujur penampang", 94.0, 142.0, (94.0, 142.0), 1.0, help="Persempit ke satu busur, misalnya 100–115 untuk Sumatra–Jawa, untuk melihat pita Benioff.")
        st.plotly_chart(grafik.penampang_subduksi(gempa, *lon_rentang), width="stretch")
    with st.expander("Mengapa kedalaman penting?"):
        st.markdown(
            """
            Gempa **dangkal (< 70 km)** paling merusak karena energinya sampai ke permukaan tanpa banyak teredam; hampir semua gempa yang
            dirasakan di Indonesia ada di kelas ini. Gempa **menengah dan dalam** terjadi di dalam lempeng samudra yang menunjam di bawah
            Indonesia. Pada penampang bujur × kedalaman, lempeng itu muncul sebagai pita miring yang semakin dalam menjauhi palung,
            dikenal sebagai **zona Wadati–Benioff**. Laut Banda dan Laut Flores adalah tempat gempa terdalam di Indonesia (hingga 600 km lebih).
            """
        )

    st.markdown("#### Waktu")
    c5, c6 = st.columns(2)
    c5.plotly_chart(grafik.garis_waktu_harian(gempa), width="stretch")
    c6.plotly_chart(grafik.grafik_energi(gempa), width="stretch")
    c7, c8 = st.columns(2)
    c7.plotly_chart(grafik.grafik_per_jam(gempa), width="stretch")
    c8.plotly_chart(grafik.grafik_jeda(gempa), width="stretch")
    jeda = analisis.jeda_antar_gempa(gempa)
    if not jeda.empty:
        st.markdown(
            f"Pada jendela ini, median jeda antar gempa adalah **{jeda.median():.0f} menit** dan rata-rata **{jeda.mean():.0f} menit**; jeda terpanjang "
            f"**{jeda.max() / 60:.1f} jam**. Sebaran per jam kejadian hampir rata, karena tektonik tidak mengenal siang dan malam. "
            f"Total energi yang dilepas setara **{ring['energi_hiroshima']:.1f} bom Hiroshima**, dan hampir seluruhnya berasal dari beberapa gempa terbesar saja: "
            f"satu kenaikan magnitudo berarti energi sekitar 32 kali lipat."
        )

    st.markdown("#### Ruang")
    zona = analisis.zona_aktif(gempa)
    c9, c10 = st.columns([1.2, 1])
    c9.plotly_chart(grafik.grafik_zona(zona), width="stretch")
    with c10:
        st.markdown("**Zona paling ramai**")
        st.dataframe(
            zona.rename(columns={"lat": "Lintang", "lon": "Bujur", "jumlah": "Gempa", "m_maks": "M maks", "kedalaman_median": "Kedalaman median (km)", "label": "Wilayah"}),
            hide_index=True,
            width="stretch",
            column_config={"Kedalaman median (km)": st.column_config.NumberColumn(format="%.0f"), "M maks": st.column_config.NumberColumn(format="%.1f")},
        )


# ---------------------------------------------------------------------------
# Tab Gunung Api
# ---------------------------------------------------------------------------

with tab_gunung:
    g1, g2 = st.columns([1, 1.4])
    g1.plotly_chart(grafik.grafik_level_gunung(gunung), width="stretch")
    with g2:
        st.markdown("**Gunung api Level II ke atas**")
        aktif = gunung[gunung["level"] >= 2].sort_values(["level", "nama"], ascending=[False, True])
        st.dataframe(
            aktif[["nama", "provinsi", "level", "status", "elevasi_m", "url_laporan"]].rename(
                columns={"nama": "Gunung", "provinsi": "Provinsi", "level": "Level", "status": "Status", "elevasi_m": "Elevasi (m)", "url_laporan": "Laporan"}
            ),
            hide_index=True,
            width="stretch",
            height=330,
            column_config={"Laporan": st.column_config.LinkColumn(display_text="MAGMA")},
        )
    st.markdown("#### Gempa di sekitar gunung api")
    radius = st.slider("Radius pencarian (km)", 20, 150, 50, 10)
    sekitar = analisis.gempa_sekitar_gunung(gempa, gunung, radius)
    sekitar = sekitar[sekitar["jumlah_gempa"] > 0]
    if sekitar.empty:
        st.info("Tidak ada gempa dalam radius itu dari gunung api mana pun pada jendela data ini.")
    else:
        st.dataframe(
            sekitar[["nama", "provinsi", "level", "status", "jumlah_gempa", "m_maks"]].rename(
                columns={"nama": "Gunung", "provinsi": "Provinsi", "level": "Level", "status": "Status", "jumlah_gempa": f"Gempa ≤ {radius} km", "m_maks": "M maks"}
            ),
            hide_index=True,
            width="stretch",
            column_config={"M maks": st.column_config.NumberColumn(format="%.1f")},
        )
    st.markdown(
        '<p class="catatan">Gempa tektonik di dekat gunung api tidak otomatis berarti gunung itu akan meletus. Gempa vulkanik yang dipakai PVMBG untuk menaikkan level '
        "umumnya terlalu kecil untuk masuk katalog USGS/BMKG. Tabel ini sekadar menunjukkan di mana dua sistem itu bertumpang tindih.</p>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Tab Data & Sumber
# ---------------------------------------------------------------------------

with tab_data:
    tampil = analisis.gunung_terdekat(gempa, gunung)
    tampil = tampil[["waktu_wib", "magnitudo", "kedalaman_km", "kelas_kedalaman", "lat", "lon", "wilayah", "gunung_terdekat", "jarak_gunung_km", "sumber", "keterangan", "url"]]
    st.dataframe(
        tampil.rename(
            columns={
                "waktu_wib": "Waktu (WIB)", "magnitudo": "M", "kedalaman_km": "Kedalaman (km)", "kelas_kedalaman": "Kelas", "lat": "Lintang", "lon": "Bujur",
                "wilayah": "Wilayah", "gunung_terdekat": "Gunung terdekat", "jarak_gunung_km": "Jarak (km)", "sumber": "Sumber", "keterangan": "Keterangan", "url": "Tautan",
            }
        ),
        hide_index=True,
        width="stretch",
        height=420,
        column_config={
            "Waktu (WIB)": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
            "Kedalaman (km)": st.column_config.NumberColumn(format="%.0f"),
            "Jarak (km)": st.column_config.NumberColumn(format="%.0f"),
            "M": st.column_config.NumberColumn(format="%.1f"),
            "Tautan": st.column_config.LinkColumn(display_text="buka"),
        },
    )
    csv = tampil.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Unduh CSV", csv, file_name=f"gempa_indonesia_{datetime.now(timezone.utc):%Y%m%d}.csv", mime="text/csv")
    st.markdown(
        """
        **Sumber**

        | Sumber | Isi | Tautan |
        |---|---|---|
        | BMKG | 15 gempa M5+ terkini dan gempa dirasakan (JSON terbuka) | [data.bmkg.go.id](https://data.bmkg.go.id/) |
        | USGS | Katalog gempa global (FDSN Event API), dipotong kotak 12°LS–7°LU, 94°–142°BT | [earthquake.usgs.gov](https://earthquake.usgs.gov/fdsnws/event/1/) |
        | MAGMA Indonesia (PVMBG) | Tingkat aktivitas 69 gunung api (Level I–IV) | [magma.esdm.go.id](https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas) |
        | Smithsonian GVP | Koordinat dan elevasi gunung api | [volcano.si.edu](https://volcano.si.edu/) |

        > ⚠️ **Disclaimer.** Aplikasi ini menampilkan ulang data publik untuk tujuan edukasi dan portofolio. Ia bukan sistem peringatan dini dan
        > tidak berafiliasi dengan BMKG, PVMBG, atau USGS. Magnitudo dan lokasi antar lembaga dapat berbeda; gunakan sumber resmi untuk keputusan apa pun.
        """
    )
    if hasil.kesalahan:
        st.markdown("**Catatan pengambilan data:** " + " · ".join(hasil.kesalahan))


# ---------------------------------------------------------------------------
# Tab Cara Kerja
# ---------------------------------------------------------------------------

with tab_cara:
    st.markdown(
        """
        #### Alur data

        ```
        BMKG JSON ─┐
        USGS GeoJSON ├─► src/sumber.py ──► DataFrame standar ──► src/analisis.py ──► src/grafik.py (Plotly)
        MAGMA HTML ─┘      (parse, gabung,      (10 kolom)          (kelas kedalaman,      src/peta.py (Folium)
                            dedup, fallback)                         b-value, energi,      app.py (Streamlit)
        data/sample/* ──────┘                                        jarak ke gunung)
        ```

        1. **Ambil.** Tiga permintaan HTTP sederhana. BMKG dan USGS memberi JSON; MAGMA hanya menyediakan halaman HTML, sehingga dibaca dengan ekspresi reguler.
        2. **Normalisasi.** Setiap sumber dipetakan ke kolom yang sama: `waktu_utc, lat, lon, magnitudo, kedalaman_km, wilayah, sumber`. Kedalaman BMKG berbentuk teks `"10 km"`, sehingga angkanya diambil dulu.
        3. **Gabung dan dedup.** USGS dan BMKG sering mencatat gempa yang sama dengan selisih detik dan beberapa kilometer. Dua catatan dianggap satu bila jatuh di jendela 2 menit dan setengah derajat yang sama.
        4. **Fallback.** Jika salah satu sumber gagal, bagian itu diganti berkas contoh di `data/sample/`, dan spanduk peringatan muncul di atas.
        5. **Analisis.** Kelas kedalaman, energi (`log10 E = 1,5M + 4,8`), b-value Gutenberg–Richter, jeda antar gempa, gunung api terdekat (haversine), dan kotak 2°×2° paling ramai.
        6. **Tampil.** Folium menggambar peta di atas tile gelap; Plotly menggambar grafik; Streamlit menyusun semuanya dan menyimpan hasil pengambilan selama 10 menit.

        Penjelasan lebih panjang ada di `docs/BELAJAR.md`, dan latihannya di `docs/LATIHAN.md`.
        """
    )
