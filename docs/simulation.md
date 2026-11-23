# Fondasi prototipe simulasi

## Aliran data

Browser meminta katalog melalui proxy Vite lokal. FastAPI membaca katalog yang tersimpan bersama kode API dan mengembalikannya sebagai JSON. Browser menampilkan kasus, sumber tiruan, dan profil perangkat terkait. Vite dibatasi pada loopback dan meneruskan `/api` ke FastAPI pada `127.0.0.1:8000`.

Katalog berisi 20 kasus tetap dengan Case ID berbeda. Dua kasus menggunakan label yang sama untuk menguji bahwa label hanyalah referensi. Generator Python memilih tiga kasus per workspace dengan seed yang sama untuk menghasilkan pilihan dengan urutan yang sama. Android menyediakan sampel metadata sintetis. Profil iPhone menyatakan kapabilitas contoh tidak didukung. Kedua profil adalah fixture dan tidak menunjukkan kemampuan perangkat nyata.

## Model ancaman awal

| Batas kepercayaan | Risiko | Kontrol prototipe dan pekerjaan berikutnya |
| --- | --- | --- |
| Browser → API | Permintaan diubah atau label berisi konten aktif | Endpoint lokal hanya membaca fixture. React merender nilai sebagai teks. Untuk fitur impor, validasi skema dan izin per kasus di API sebelum menyimpan data. |
| API → worker | Job diputar ulang atau pekerjaan berjalan setelah izin dicabut | Worker belum terhubung. Sebelum antrean diaktifkan, gunakan kunci idempotensi, simpan checkpoint, dan periksa otorisasi ketika job berjalan. |
| Desktop → API/cloud | Perangkat hilang atau identitas perangkat dipalsukan | Desktop dan cloud belum terhubung. Enrollment, mTLS, dan sesi offline harus diuji sebelum sinkronisasi. |
| Desktop → mobile | Akses melampaui persetujuan atau kapabilitas resmi | Profil saat ini berupa fixture lokal. Integrasi perangkat membutuhkan consent spesifik yang dapat dicabut, izin per kapabilitas, dan penghentian pekerjaan saat consent dicabut. |
| Worker → sumber eksternal | URL sewenang-wenang, pembatasan penggunaan sumber, atau data berbahaya | Profil sumber tidak menyimpan URL yang dapat dipanggil. Konektor mendatang memerlukan daftar tujuan yang disetujui, pembatasan permintaan, dan validasi respons. |
| Cloud → database/arsip | Bukti berubah atau akses lintas kasus | Penyimpanan bukti belum ada. Sebelum data diterima, verifikasi izin, referensi bukti immutable, manifest bertanda tangan, dan pemulihan yang diaudit. |

Prototipe ini tidak menerima unggahan atau data pribadi, tidak mengakses jaringan sumber eksternal, dan tidak mengakses perangkat. Keputusan SLA insiden, vendor cloud, metode MFA, dan kapabilitas perangkat nyata masih terbuka sebagaimana dicatat di [rencana pengerjaan](../task.md).

## Kontrak HTTP v1

- `GET /api/v1/health` mengembalikan `{"status":"ok","mode":"SYNTHETIC"}`.
- `GET /api/v1/simulation/catalog` mengembalikan `mode`, `cases`, `sources`, dan `devices`.
- `GET /api/v1/simulation/cases/SYN-001` mengembalikan satu kasus. ID yang tidak dikenal menghasilkan HTTP 404 dengan isi `{"code":"case_not_found","message":"Synthetic case not found."}`.
- API menghasilkan UUID versi 4 baru di header `X-Correlation-ID` pada setiap respons prototipe yang diterima melalui middleware.
- Endpoint simulasi bersifat read-only dan tidak memerlukan kunci idempotensi. Untuk operasi tulis mendatang, dokumentasikan semantik `Idempotency-Key` dan timestamp RFC 3339 UTC bersama endpoint yang menggunakannya.

## Bukti saat ini

Tes API mencakup katalog 20 kasus, referensi profil, ID kasus yang berbeda untuk label ganda, respons 404, penolakan tulis, ID korelasi, dan generator seed. Katalog hanya mendeskripsikan skenario antrean, consent, integritas, dan sinkronisasi. Skenario tersebut belum menjalankan alur operasional di Gate A.
