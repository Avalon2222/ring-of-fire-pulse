# 🏋️ Latihan

Diurutkan dari mudah ke menantang. Tiap latihan punya petunjuk dan kunci yang bisa dibuka. Usahakan mencoba
minimal 10 menit sebelum membuka kunci. Setelah tiap latihan, jalankan `python -m pytest tests/` dan
`streamlit run app.py`.

---

### Latihan 1 — Menambah gunung api (cukup edit CSV) ⭐

MAGMA memantau 69 gunung api, tetapi Indonesia punya 127. Tambahkan **Gunung Krakatau** (induk Anak Krakatau,
sisa kaldera 1883) ke `data/gunung_api.csv`: lat `-6.102`, lon `105.423` akan bertabrakan dengan Anak Krakatau,
jadi pakai Pulau Rakata `-6.150`, lon `105.440`, elevasi `813`, provinsi `Lampung`, sumber `Smithsonian GVP`.
Buka tab Gunung Api dan pastikan ia muncul sebagai Level I.

<details><summary>Petunjuk</summary>
Satu baris baru di akhir CSV. Perhatikan urutan kolom: nama, lat, lon, elevasi_m, provinsi, sumber.
</details>

<details><summary>Kunci</summary>

```
Rakata,-6.150,105.440,813,Lampung,Smithsonian GVP
```

Dua tes akan **gagal**: `test_gunung_api_statis_valid` dan `test_gabung_gunung_api_menempelkan_level`
mengharapkan 69 baris. Ubah angka 69 menjadi 70 di keduanya. Tes yang gagal karena asumsi lama adalah tes yang
bekerja dengan benar.
</details>

---

### Latihan 2 — Jam paling "ramai" ⭐

Di tab Pola, grafik per jam menunjukkan jam dengan gempa terbanyak. Tambahkan satu kalimat di bawah grafik yang
menyebut jam itu, misalnya "Jam paling ramai: 14:00 WIB (11 gempa)". Fungsi `analisis.per_jam` sudah ada.

<details><summary>Petunjuk</summary>
`per_jam` mengembalikan DataFrame kolom `jam` dan `jumlah`. `idxmax()` memberi indeks baris dengan nilai terbesar.
</details>

<details><summary>Kunci</summary>

```python
jam = analisis.per_jam(gempa)
puncak = jam.loc[jam["jumlah"].idxmax()]
st.caption(f"Jam paling ramai: {int(puncak['jam']):02d}:00 WIB ({int(puncak['jumlah'])} gempa).")
```

Lalu tanyakan pada diri sendiri: apakah 11 gempa pada satu jam, dari 150 gempa dalam 30 hari, benar-benar pola?
Bab 2.4 di BELAJAR.md menjawabnya.
</details>

---

### Latihan 3 — Filter berdasarkan sumber ⭐⭐

Tambahkan `multiselect` di sidebar untuk memilih sumber (`USGS`, `BMKG M5+`, `BMKG dirasakan`), dan saring
`gempa` sesuai pilihan.

<details><summary>Petunjuk</summary>
Tiru baris `kelas = st.multiselect(...)` dan tambahkan satu syarat lagi di ekspresi filter `gempa = gempa_semua[...]`.
</details>

<details><summary>Kunci</summary>

```python
# sidebar
sumber_pilih = st.multiselect("Sumber", sorted(gempa_semua["sumber"].unique()), default=sorted(gempa_semua["sumber"].unique()))

# filter
gempa = gempa_semua[
    (gempa_semua["magnitudo"] >= mag_min)
    & (gempa_semua["kelas_kedalaman"].isin(kelas))
    & (gempa_semua["sumber"].isin(sumber_pilih))
].reset_index(drop=True)
```

Perhatikan: `gempa_semua` harus sudah dimuat sebelum sidebar membaca `unique()`-nya. Pindahkan widget ini ke
bawah pemanggilan `muat(...)`, atau bungkus dalam `with st.sidebar:` kedua.
</details>

---

### Latihan 4 — Satuan energi yang lebih akrab ⭐⭐

"Bom Hiroshima" memberi gambaran, tetapi tambahkan satu pembanding lagi di `analisis.py`: konsumsi listrik
Indonesia sekitar **300 TWh per tahun** (1 TWh = 3,6 × 10¹⁵ J). Buat fungsi `setara_listrik_hari(joule)` yang
mengembalikan berapa hari konsumsi listrik nasional yang setara, lalu tampilkan di kartu KPI.

<details><summary>Petunjuk</summary>
Energi per hari = 300 × 3,6 × 10¹⁵ / 365 J. Bagi energi gempa dengan angka itu.
</details>

<details><summary>Kunci</summary>

```python
ENERGI_LISTRIK_HARI_J = 300 * 3.6e15 / 365   # ~ 2,96 x 10^15 J

def setara_listrik_hari(joule: float) -> float:
    return joule / ENERGI_LISTRIK_HARI_J
```

Untuk 30 hari data dengan M maks 5,7, hasilnya biasanya sekitar 0,05–0,1 hari, alias beberapa jam listrik
nasional. Gempa Aceh 2004 (M9,1) melepaskan ~ 10¹⁸ J, setara satu tahun listrik Indonesia.
Tambahkan tes di `test_analisis.py` yang memeriksa `setara_listrik_hari(2.96e15) ≈ 1`.
</details>

---

### Latihan 5 — Lingkaran radius di sekitar gunung Siaga ⭐⭐

Untuk tiap gunung api Level III atau IV, gambar lingkaran radius 50 km di peta (`folium.Circle`, satuan meter).
Beri warna sesuai level dan masukkan ke `FeatureGroup` sendiri bernama "Radius 50 km (Siaga/Awas)".

<details><summary>Petunjuk</summary>
Di `buat_peta`, setelah lapisan gunung api: saring `gunung[gunung["level"] >= 3]`, lalu loop
`folium.Circle(location=..., radius=50_000, color=..., fill=True, fill_opacity=0.08)`.
</details>

<details><summary>Kunci</summary>

```python
siaga = gunung[gunung["level"] >= 3]
if not siaga.empty:
    fg_radius = folium.FeatureGroup(name="Radius 50 km (Siaga/Awas)", show=True)
    for _, r in siaga.iterrows():
        folium.Circle(
            location=(r["lat"], r["lon"]), radius=50_000,
            color=WARNA_LEVEL[int(r["level"])], weight=1, fill=True, fill_opacity=0.08,
            tooltip=f"50 km dari {r['nama']}",
        ).add_to(fg_radius)
    fg_radius.add_to(m)
```
</details>

---

### Latihan 6 — Mc yang lebih jujur ⭐⭐⭐

Metode kelengkungan maksimum cenderung **menaksir Mc terlalu rendah** sekitar 0,2. Tambahkan parameter
`koreksi: float = 0.2` pada `magnitudo_lengkap` yang ditambahkan ke hasil, lalu lihat bagaimana b-value berubah
di aplikasi. Perbarui tes agar tetap hijau.

<details><summary>Petunjuk</summary>
Tes `test_b_value_mendekati_satu_untuk_data_sintetis` memanggil `b_value(..., mc=3.0)` secara eksplisit, jadi
tidak terpengaruh. Tetapi perilaku bawaan `b_value` tanpa `mc` berubah; tambahkan tes baru yang memeriksa bahwa
`magnitudo_lengkap(seri, koreksi=0.2)` = `magnitudo_lengkap(seri, koreksi=0)` + 0,2.
</details>

<details><summary>Kunci</summary>

```python
def magnitudo_lengkap(mag, lebar_bin=0.1, koreksi=0.2):
    if mag.empty:
        return float("nan")
    bins = (mag / lebar_bin).round().astype(int)
    return float(bins.value_counts().idxmax() * lebar_bin + koreksi)
```

Dengan Mc lebih tinggi, jumlah gempa yang dipakai turun dan galat `b` naik. Itu harga kejujuran: lebih sedikit
data, ketidakpastian lebih besar, tetapi tanpa bias dari gempa kecil yang kurang tercatat.
</details>

---

### Latihan 7 — Deduplikasi yang lebih cermat ⭐⭐⭐

`gabung_gempa` memakai kotak waktu 2 menit dan setengah derajat. Dua gempa susulan dalam 90 detik dan 30 km akan
digabung padahal berbeda. Tulis ulang dedup berdasarkan **jarak sebenarnya**: dua baris dianggap sama bila selisih
waktu < 60 detik **dan** jarak haversine < 50 km. Buat tesnya: dua gempa 90 detik terpisah harus tetap dua baris.

<details><summary>Petunjuk</summary>
Urutkan berdasarkan waktu. Untuk tiap baris, bandingkan hanya dengan baris-baris sebelumnya yang jatuh dalam 60
detik (gunakan `searchsorted` pada kolom waktu bertipe int64) dan hitung haversine ke mereka. Simpan indeks yang
lolos. O(N·k) dengan k kecil.
</details>

<details><summary>Kunci</summary>

```python
def gabung_gempa_cermat(*bingkai, detik=60, km=50):
    isi = [b for b in bingkai if b is not None and not b.empty]
    if not isi:
        return _bingkai_kosong()
    df = pd.concat(isi, ignore_index=True)
    urutan = {"USGS": 0, "BMKG M5+": 1, "BMKG dirasakan": 2}
    df["_urut"] = df["sumber"].map(urutan).fillna(9)
    df = df.sort_values(["waktu_utc", "_urut"]).reset_index(drop=True)
    t = df["waktu_utc"].astype("int64").to_numpy() // 10**9
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    simpan, terpakai = [], []           # terpakai: indeks baris yang sudah lolos
    from src.analisis import haversine_km
    for i in range(len(df)):
        awal = np.searchsorted(t, t[i] - detik)
        kandidat = [j for j in terpakai if j >= awal]
        if kandidat and (haversine_km(lat[i], lon[i], lat[kandidat], lon[kandidat]) < km).any():
            continue
        simpan.append(i); terpakai.append(i)
    return df.loc[simpan].drop(columns="_urut").sort_values("waktu_utc", ascending=False).reset_index(drop=True)
```

Karena diurutkan berdasarkan waktu lalu `_urut`, baris USGS tetap menang bila waktunya sama. Untuk kasus
waktu BMKG lebih awal beberapa detik dari USGS, perlu logika tambahan; cukup sebutkan keterbatasannya di
docstring.
</details>

---

### Latihan 8 — Deteksi kawanan gempa ⭐⭐⭐⭐

Kawanan (*swarm*) adalah kelompok gempa yang berdekatan dalam ruang dan waktu tanpa satu gempa utama yang jelas.
Tulis `analisis.kawanan(df, km=30, jam=48, minimal=5)` yang mengembalikan daftar kelompok: tiap kelompok berisi
indeks gempa, pusat (lat, lon), jumlah, dan M maks. Tampilkan kelompok terbesar sebagai poligon atau lingkaran di
peta.

<details><summary>Petunjuk</summary>
Ini masalah komponen terhubung: buat sisi antara dua gempa jika jarak < km dan selisih waktu < jam, lalu
telusuri graf (BFS/DFS atau `scipy.sparse.csgraph.connected_components`). Matriks jarak N×N dari `haversine_km`
dengan broadcasting sudah cukup untuk N beberapa ratus.
</details>

<details><summary>Kunci</summary>

```python
def kawanan(df, km=30.0, jam=48.0, minimal=5):
    if len(df) < minimal:
        return []
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    t = df["waktu_utc"].astype("int64").to_numpy() / 3.6e12       # jam
    dekat = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :]) < km
    serempak = np.abs(t[:, None] - t[None, :]) < jam
    tetangga = dekat & serempak
    np.fill_diagonal(tetangga, False)
    label = -np.ones(len(df), dtype=int)
    hasil = []
    for awal in range(len(df)):
        if label[awal] >= 0:
            continue
        tumpukan, anggota = [awal], []
        label[awal] = awal
        while tumpukan:
            i = tumpukan.pop(); anggota.append(i)
            for j in np.flatnonzero(tetangga[i]):
                if label[j] < 0:
                    label[j] = awal; tumpukan.append(j)
        if len(anggota) >= minimal:
            sub = df.iloc[anggota]
            hasil.append({"indeks": anggota, "lat": sub["lat"].mean(), "lon": sub["lon"].mean(),
                          "jumlah": len(anggota), "m_maks": sub["magnitudo"].max()})
    return sorted(hasil, key=lambda k: -k["jumlah"])
```

Uji dengan data buatan: 8 gempa dalam 10 km dan 5 jam, plus 20 gempa tersebar acak, harus menghasilkan tepat
satu kawanan beranggota 8. Lalu jalankan pada data langsung dan periksa apakah kawanan terbesar berada di dekat
gunung api berlevel II ke atas; sering kali ya, sering kali tidak.
</details>

---

### Latihan 9 — Katalog yang tumbuh ⭐⭐⭐⭐

Jendela USGS dibatasi 30 hari. Buat `scripts/simpan_harian.py` yang mengambil USGS 2 hari terakhir dan
menyisipkannya ke SQLite `data/katalog.sqlite` (tabel `gempa`, kunci unik `id`). Lalu tambahkan opsi
"Arsip lokal" di sidebar yang membaca tabel itu. Setelah beberapa bulan berjalan lewat Task Scheduler atau cron,
Anda punya katalog sendiri untuk menghitung b-value per bulan.

<details><summary>Petunjuk</summary>
`sqlite3` ada di pustaka standar. `INSERT OR IGNORE` menangani duplikat `id`. `pd.read_sql` membaca kembali.
Simpan `waktu_utc` sebagai teks ISO 8601 agar mudah diurutkan.
</details>

<details><summary>Kunci</summary>

```python
import sqlite3
con = sqlite3.connect(DIR_DATA / "katalog.sqlite")
con.execute("""CREATE TABLE IF NOT EXISTS gempa (
    id TEXT PRIMARY KEY, waktu_utc TEXT, lat REAL, lon REAL, magnitudo REAL,
    kedalaman_km REAL, wilayah TEXT, sumber TEXT, keterangan TEXT, url TEXT)""")
df = ambil_usgs(hari=2)
df["waktu_utc"] = df["waktu_utc"].dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
con.executemany("INSERT OR IGNORE INTO gempa VALUES (?,?,?,?,?,?,?,?,?,?)", df[KOLOM_GEMPA].itertuples(index=False))
con.commit()
```

Membaca kembali: `pd.read_sql("SELECT * FROM gempa", con, parse_dates={"waktu_utc": {"utc": True}})`.
</details>
