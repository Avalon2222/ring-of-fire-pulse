# Sumber data & catatan metodologi

Seluruh data berasal dari layanan publik yang dapat diakses siapa pun tanpa kunci API. Tidak ada data yang
dikumpulkan dari pengguna, dan tidak ada data yang disimpan selain berkas contoh di `data/sample/`.

## Sumber langsung

| Sumber | Alamat | Isi | Format | Pembaruan |
|---|---|---|---|---|
| BMKG, gempa M5+ terkini | `https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.json` | 15 gempa terakhir bermagnitudo ≥ 5 | JSON | setiap ada gempa |
| BMKG, gempa dirasakan | `https://data.bmkg.go.id/DataMKG/TEWS/gempadirasakan.json` | 15 gempa terakhir yang dilaporkan dirasakan, beserta skala MMI | JSON | setiap ada gempa |
| USGS FDSN Event | `https://earthquake.usgs.gov/fdsnws/event/1/query` | Katalog gempa global; dipotong kotak 12°LS–7°LU, 94°–142°BT, M ≥ 2,5, 30 hari terakhir | GeoJSON | menit |
| MAGMA Indonesia (PVMBG, Badan Geologi) | `https://magma.esdm.go.id/v1/gunung-api/tingkat-aktivitas` | Tingkat aktivitas 69 gunung api: Level I Normal – Level IV Awas | HTML | harian |

## Data statis

`data/gunung_api.csv` berisi 69 gunung api yang dipantau MAGMA beserta koordinat dan elevasi dari basis data
Smithsonian Global Volcanism Program (volcano.si.edu). Koordinat dibulatkan ke tiga desimal; cukup untuk peta
skala nasional. Beberapa nama di MAGMA berbeda dari GVP (misalnya "Kie Besi" untuk Makian, "Sangeangapi" untuk
Sangeang Api). Nama di CSV mengikuti ejaan MAGMA agar pencocokan otomatis berhasil.

## Data contoh (`data/sample/`)

Salinan dari keempat sumber di atas, diambil pada tanggal yang tercatat di `meta.json`. Dipakai saat:

1. pengguna memilih mode offline di sidebar,
2. salah satu sumber gagal diambil (waktu tunggu 20 detik), atau
3. pengujian dijalankan, agar `pytest` tidak bergantung pada jaringan.

Perbarui dengan `python scripts/perbarui_sample.py`.

## Catatan metodologi

- **Zona waktu.** Semua waktu disimpan dalam UTC dan ditampilkan dalam WIB. Indonesia memiliki tiga zona waktu;
  WIB dipilih karena BMKG memakainya di umpan publik.
- **Deduplikasi.** USGS dan BMKG sering mencatat gempa yang sama dengan selisih detik dan beberapa kilometer.
  Dua catatan dianggap satu bila jatuh di jendela 2 menit yang sama dan koordinatnya membulat ke setengah
  derajat yang sama. USGS diutamakan karena katalognya paling lengkap. Cara ini sederhana dan bisa saja
  menggabungkan dua gempa berbeda yang sangat berdekatan (misalnya gempa susulan dalam dua menit).
- **Magnitudo.** USGS memakai beberapa jenis magnitudo (mb, mww, ml) dan BMKG memakai skalanya sendiri;
  semuanya dicampur begitu saja di sini. Untuk gempa kecil selisihnya bisa 0,3 atau lebih.
- **Energi.** `log10 E[J] = 1,5 M + 4,8` (Gutenberg & Richter, 1956). Satu bom Hiroshima dianggap setara
  15 kiloton TNT ≈ 6,3 × 10¹³ J. Perbandingan ini hanya untuk memberi gambaran skala.
- **b-value.** Penaksir kemungkinan maksimum Aki (1965) dengan koreksi lebar bin 0,1; galat mengikuti
  Shi & Bolt (1982). Magnitudo kelengkapan (Mc) ditaksir dengan metode kelengkungan maksimum, yaitu bin
  dengan jumlah gempa terbanyak. Pada jendela 30 hari dengan ratusan gempa, nilainya kasar.
- **Palung.** Garis palung di peta digambar tangan dari peta tektonik umum, hanya sebagai orientasi.
- **Gempa di sekitar gunung api.** Jarak haversine dari episentrum ke puncak. Kedekatan tidak berarti
  hubungan sebab-akibat; gempa vulkanik yang dipakai PVMBG untuk menaikkan level umumnya terlalu kecil untuk
  masuk katalog USGS/BMKG.

## Disclaimer

Proyek ini menampilkan ulang data publik untuk tujuan edukasi dan portofolio. Ia bukan sistem peringatan dini,
tidak berafiliasi dengan BMKG, PVMBG, Badan Geologi, atau USGS, dan tidak boleh dipakai untuk keputusan
keselamatan. Rujuk selalu ke sumber resmi: [bmkg.go.id](https://www.bmkg.go.id/),
[magma.esdm.go.id](https://magma.esdm.go.id/), [earthquake.usgs.gov](https://earthquake.usgs.gov/).
