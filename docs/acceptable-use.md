# Batas penggunaan MARGONO

## Penggunaan yang diizinkan

- Prototipe lokal menggunakan katalog baca-saja untuk meninjau kasus keamanan siber sintetis dan membuat rencana simulasi deterministik. Gunakan Case ID dari katalog dan seed numerik. Label kasus berfungsi sebagai referensi baris.
- Integrasi mendatang hanya boleh memeriksa indikator keamanan teknis dalam cakupan organisasi atau perangkat yang memiliki otorisasi. Penggunaan sumber eksternal memerlukan persetujuan dan peninjauan syarat penggunaan. Pemeriksaan perangkat memerlukan persetujuan pemilik yang spesifik, sukarela, terdokumentasi, dan dapat dicabut.
- Analis menilai relevansi indikator dan meninjau bukti sebelum publikasi laporan. Catat keterbatasan sumber atau kapabilitas perangkat bersama hasil pemeriksaan.

Di luar ruang lingkup MARGONO ialah pencarian akun personal berdasarkan nama, inferensi atribut sensitif, penilaian kelayakan personel, pengambilan pesan atau media pribadi, akses tanpa persetujuan, dan bypass kontrol platform.

## Contoh pemberitahuan persetujuan sintetis

> **SIMULASI.** Pemeriksaan ini terbatas pada metadata versi sistem di profil Android sintetis dan digunakan untuk melatih alur tinjauan indikator teknis. Anda dapat menolak atau mencabut persetujuan kapan saja melalui examiner yang menangani sesi. Penolakan atau pencabutan menghentikan pemeriksaan yang terkait. Hasil latihan dilihat oleh examiner yang menangani kasus simulasi.

| Unsur | Contoh sintetis |
| --- | --- |
| Kasus dan sesi | `SYN-011` dan `SYN-SESSION-001` |
| Pencatat | `SYN-EXAMINER-001` |
| Tujuan | Latihan tinjauan indikator teknis |
| Cakupan | Metadata versi sistem profil `DEV-ANDROID` |
| Keputusan dan waktu | `granted` pada `2026-01-01T00:00:00Z` |
| Pencabutan | Bila dicabut, rekam `revoked_at`, hentikan pekerjaan yang terkait, dan catat tindakan pada audit. |

Contoh ini mendeskripsikan alur consent yang akan diterapkan pada sesi pemeriksaan. API katalog saat ini menyajikan profil sintetis yang sudah disiapkan.

## Rencana pengujian

| Pemeriksaan | Hasil yang diharapkan |
| --- | --- |
| GET rencana dengan seed yang sama | Case ID sintetis yang sama dalam urutan yang sama. |
| GET rencana dengan input di luar kontrak | HTTP 422 dengan pesan umum. Parameter seperti nama, profil, sumber, atau ID perangkat tidak diteruskan ke generator. |
| Dua label kasus identik | Kedua kasus tetap memiliki Case ID berbeda. |
| Permintaan tulis ke endpoint simulasi | HTTP 405. |
| Consent ditolak atau dicabut pada alur pemeriksaan mendatang | Pekerjaan terkait berhenti dan status tercatat. Pengujian ini diperlukan ketika alur tersebut tersedia. |

## Checklist review perubahan

- [ ] Operasi memiliki tujuan keamanan yang objektif dan ruang lingkup yang terdokumentasi.
- [ ] Tes menggunakan fixture sintetis dan menolak input di luar kontrak yang dapat memicu pemrosesan tambahan.
- [ ] Respons menjaga kerahasiaan input yang ditolak dan menandai data simulasi dengan jelas.
- [ ] Jika perubahan menambah akses ke perangkat atau sumber, tinjau izin, batas data, pencabutan consent, dan kebutuhan audit sebelum mengaktifkannya.
