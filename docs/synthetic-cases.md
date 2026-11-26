# Alur kasus sintetis lokal

Siapkan [PostgreSQL lokal](database.md) dan terapkan migrasi. Siapkan akun latihan dari terminal tepercaya di direktori `services/api`.

```bash
uv run --locked python -m margono_api.provision latihan-osint osint_analyst
uv run --locked python -m margono_api.provision latihan-supervisor supervisor
uv run --locked python -m margono_api.provision latihan-forensik forensic_examiner
```

Pemberian akun melalui CLI ditujukan untuk pengembangan lokal. Gunakan kata sandi latihan unik minimal 12 karakter. Jalankan API dengan `MARGONO_DATABASE_URL` yang sama dan buka **Kasus simulasi tersimpan** di web. Masuk sebagai OSINT Analyst, pilih fixture, isi tujuan dan ruang lingkup, lalu buat kasus. Pilih CSV UTF-8 atau XLSX sintetis dan kolom label, atau masukkan satu label manual per baris. Tinjau baris lalu konfirmasi. Pilih kolom dari header yang dibaca API. Kolom `Nama` menjadi pilihan awal jika tersedia. Pratinjau menandai label kosong, lebar baris yang salah, dan duplikat. Duplikat tetap disimpan sebagai baris terpisah. Pratinjau dan konfirmasi terikat ke Case ID asal. Berpindah kasus membuang pratinjau lokal dan mengabaikan respons lama.

Panel **Riwayat impor** menampilkan waktu, kolom yang dipilih, jumlah baris valid, tidak valid, atau menunggu, dan SHA-256 jika tersedia. Bukti bisa diunduh oleh operator yang dapat membaca kasus. Riwayat dimuat per halaman dan tetap menampilkan catatan lama tanpa bukti. **Periksa batch** menampilkan baris tersimpan dan 100 peristiwa audit terakhir pada batch tersebut.

- Login menggunakan scrypt untuk kata sandi dan menyimpan hash token sesi acak di database. Sesi berlaku satu jam, diperiksa lagi pada setiap operasi, dan dapat dicabut lewat tombol **Keluar**. Token web berada di memori halaman.
- OSINT Analyst dan Forensic Examiner dapat membuat serta membaca kasus milik sendiri. Supervisor dapat membaca, menutup, dan membuka kembali kasus serta memberi atau mencabut akses operator pada satu kasus terbuka. Administrator tanpa peran kasus tidak mendapat akses bukti.
- OSINT Analyst dapat mengimpor CSV, XLSX satu lembar, dan label manual untuk kasus terbuka miliknya. Sel formula XLSX tidak dipakai sebagai label. Maksimum 64 KiB, 500 baris data, 100 kolom, dan 500 karakter per label valid. Kunci `Idempotency-Key` mengulang hasil konfirmasi yang identik. Isi, format, atau kolom berbeda dengan kunci yang sama menghasilkan HTTP 409.
- Bukti impor menyimpan byte asli dan SHA-256. PostgreSQL menolak hash yang tidak sesuai serta pembaruan atau penghapusan biasa pada tabel bukti. Unduhan melalui API memeriksa hak akses dan menghitung ulang hash. Mutasi kasus, konfirmasi impor, dan siklus sesi mencatat peristiwa dan ID korelasi. Konfirmasi dan penyajian bukti yang lolos verifikasi mencatat Case ID, Import ID, actor dan ID korelasi. Peristiwa penyajian mencatat keputusan server mengirim bukti. Pengiriman byte hingga selesai dan persetujuan rilis formal memerlukan kontrol tersendiri.
- Latihan menggunakan autentikasi lokal dengan kata sandi. Build masih menerapkan pembatasan mode lokal pada [kesiapan pilot](pilot-readiness.md).

## Menjalankan worker dan review

Jalankan worker di terminal terpisah dari API. Keduanya memakai `MARGONO_DATABASE_URL` yang sama.

```bash
(cd services/api && uv run --locked python -m margono_api.synthetic_worker)
```

Opsi `--once` mengerjakan job yang sudah bisa dijalankan lalu keluar. Job yang dijadwalkan untuk retry tetap tersimpan di PostgreSQL. Untuk batch dengan baris valid, tekan **Antrekan sumber sintetis** lalu **Muat aktivitas kasus** untuk melihat status. Job sumber yang menunggu dapat dijeda atau dibatalkan. Job yang dijeda dapat dilanjutkan dan job yang gagal dapat diulang. Worker memeriksa kembali bahwa kasus terbuka sebelum membuat bukti. Commit hasil menjadi checkpoint satu langkah dan melekat pada satu Job ID. Sumber fixture hanya menghasilkan indikator `margono.test` dan metadata sintetis.

Worker kontinu membuka kembali koneksi saat PostgreSQL terputus. Jeda percobaan koneksi meningkat dari satu detik hingga maksimal 15 detik. Setelah tersambung, worker memeriksa klaim yang terputus dan melanjutkan antrean. Opsi `--once` mengembalikan kegagalan koneksi ke pemanggil.

OSINT Analyst pemilik, kolaborator OSINT Analyst dan Supervisor dapat meninjau temuan. **Muat aktivitas kasus** membuka antrean **Menunggu review**, jumlah temuan yang cocok, dan daftar job. Gunakan **Muat temuan berikutnya** atau **Muat pekerjaan berikutnya** untuk membuka halaman tambahan. Filter status membuka temuan yang sudah diputuskan. Catat keputusan dan konteks bukti. Keputusan tersimpan tidak dapat ditimpa oleh operator kedua. Laporan eksekutif memuat ringkasan. Laporan teknis memuat detail temuan dan bukti sintetis yang sesuai Case ID. Forensic Examiner dapat membuka laporan teknis pada kasus USB yang dapat diaksesnya.

Panel **Pekerjaan portal** tersedia untuk OSINT Analyst, Forensic Examiner, dan Supervisor. Daftar mengikuti akses kasus. Panel menampilkan hitungan kegagalan dan memberi tahu pengguna jika daftar hanya memuat sebagian dari total pekerjaan. OSINT Analyst dan Supervisor juga melihat jumlah temuan menunggu review. **Buka kasus** membuka kasus dari aktivitas tanpa meminta login ulang selama sesi masih aktif.

Temuan teknis dan laporan teknis sama-sama mengikuti hak baca berdasarkan peran dan workspace. OSINT Analyst dan Supervisor dapat membaca keduanya pada kasus dalam cakupannya. Forensic Examiner dapat membaca keduanya pada kasus USB dalam cakupannya. Kasus Web Intelligence yang dibagikan kepada Forensic Examiner tetap menyediakan aktivitas job dan laporan eksekutif. Temuan yang sudah diputuskan menampilkan ID peninjau dan waktu review. Rincian audit batch menampilkan aktor dan ID korelasi bila tersedia.

## Simulasi USB di web

Buka kasus dari fixture USB dengan akun Forensic Examiner yang berhak membacanya. Buka **Muat sesi perangkat**, baca disclosure dan ruang lingkup, lalu catat persetujuan atau penolakan. Hanya sesi yang disetujui bisa membuat job. Simulasi mencakup metadata Android, iPhone yang tidak didukung, penolakan, pencabutan, serta koneksi Android yang terputus. Pencabutan membatalkan job yang belum menerbitkan hasil. Worker dan pencabutan menggunakan kunci transaksi pada kasus yang sama. Hasil yang sudah disimpan tetap menjadi bagian riwayat kasus.

Jika respons keputusan hilang, **Periksa keputusan** membaca keputusan asli berdasarkan kunci operasi. **Coba lagi keputusan** mengirim keputusan yang sama dengan kunci asli jika hasil belum tersedia. Referensi tersimpan per operator dan Case ID selama sesi tab, termasuk setelah berpindah kasus, reload, dan login ulang di tab tersebut. Setelah hasil diketahui, dialog persetujuan dapat dipakai untuk mencatat keputusan baru secara sengaja.

Pada kasus terbuka dengan persetujuan aktif, Forensic Examiner dapat memilih **Ulangi mock scan** di aktivitas kasus untuk mengantrekan kembali Job ID yang gagal. Pencabutan memblokir retry. Fixture putus koneksi tetap mensimulasikan putus koneksi pada percobaan berikutnya.

Supervisor dapat memilih **Periksa audit sesi** di daftar perangkat untuk melihat keputusan, pencabutan, dan peristiwa job yang dicatat dengan referensi sesi tersebut. Aktivitas kasus dan kedua laporan memakai status antrean yang sama untuk job USB.

## API

| Operasi | Endpoint |
| --- | --- |
| Login dan logout | `POST /api/v1/sessions` dan `DELETE /api/v1/sessions/current` |
| Buat dan daftar kasus | `POST /api/v1/cases` dan `GET /api/v1/cases` dengan `before` dan `limit` opsional |
| Pulihkan hasil pembuatan | `GET /api/v1/cases/creation-receipt` dengan `Idempotency-Key` |
| Detail dan perubahan status Supervisor | `GET /api/v1/cases/{id}` dan `PATCH /api/v1/cases/{id}/status?status=closed` |
| Daftar header impor | `POST /api/v1/cases/{id}/imports/columns` |
| Riwayat impor | `GET /api/v1/cases/{id}/imports` dengan paginasi opsional `before` dan `limit` |
| Pulihkan hasil konfirmasi | `GET /api/v1/cases/{id}/imports/confirmation` dengan `Idempotency-Key` |
| Pratinjau dan konfirmasi impor | `POST /api/v1/cases/{id}/imports/preview` dan `POST /api/v1/cases/{id}/imports` |
| Unduh bukti | `GET /api/v1/cases/{id}/imports/{import_id}/evidence` |
| Baris dan audit batch | `GET /api/v1/cases/{id}/imports/{import_id}/details` |
| Kolaborasi | `GET /api/v1/cases/{id}/collaborators` dan `PUT` atau `DELETE` pada `/collaborators/{username}` |
| Antrean sumber | `POST /api/v1/cases/{id}/imports/{import_id}/jobs` dengan `Idempotency-Key` |
| Pantau dan kontrol job | `GET /api/v1/jobs`, `GET /api/v1/cases/{id}/jobs`, dan `PATCH /api/v1/cases/{id}/jobs/{job_id}?action=pause` (pilihan `resume`, `cancel`, `retry`) |
| Temuan dan dua laporan | `GET /api/v1/cases/{id}/findings`, `PATCH /api/v1/cases/{id}/findings/{finding_id}/review`, dan `GET /api/v1/cases/{id}/reports/{executive\|technical}` |
| Persetujuan dan scan sintetis | `GET` dan `POST /api/v1/cases/{id}/devices`, serta `POST` pada `/devices/{session_id}/jobs` dan `/devices/{session_id}/revoke` |
| Pulihkan keputusan consent | `GET /api/v1/cases/{id}/devices/decision` dengan `Idempotency-Key` |
| Audit sesi perangkat | `GET /api/v1/cases/{id}/devices/{session_id}/audit` untuk Supervisor |

Gunakan `Authorization: Bearer <token>` setelah login. Untuk membuat kasus, web mengirim `Idempotency-Key` baru dan memakai kunci yang sama saat mencoba ulang payload yang sama. Klien API lama tetap bisa membuat kasus tanpa header tersebut. Jika kunci dikirim, percobaan ulang oleh operator yang sama mengembalikan `201` dan respons asli, termasuk setelah kasus ditutup. Perubahan payload dengan kunci yang sama menghasilkan `409 idempotency_conflict`. Tujuan dan ruang lingkup dengan karakter kontrol menghasilkan `422` sebelum transaksi.

Jika respons hilang, browser menyimpan kunci dan sidik jari operasi selama sesi tab, termasuk setelah reload dan login ulang. Referensi pembuatan terikat pada operator. Referensi konfirmasi impor terikat pada operator dan Case ID. Isi formulir, file, dan token sesi tidak disimpan bersama referensi itu.

Jika portal menampilkan **Hasil belum diketahui**, kasus atau batch mungkin sudah tersimpan. Pilih **Periksa hasil pembuatan** untuk membuka status kasus terbaru atau **Periksa riwayat konfirmasi** untuk mencari batch berdasarkan kunci asli, termasuk jika batch sudah berada di halaman riwayat berikutnya. Kedua tombol hanya membaca hasil yang sudah tersimpan. Portal juga memeriksa batch saat kasus dibuka kembali. Jika hasil belum ditemukan, masukkan kembali isian yang sama atau pratinjau ulang impor yang sama, lalu pilih **Coba lagi**. Gunakan **Mulai pembuatan baru** atau **Mulai impor baru** untuk melepas referensi sebelumnya dan memulai operasi lain secara sengaja.

Daftar kasus tetap mengirim array. Jika halaman berikutnya tersedia, gunakan nilai header `X-Next-Cursor` sebagai parameter `before`. Tombol **Muat kasus sebelumnya** mengikuti cursor itu dan mempertahankan pilihan saat ini.

Daftar job per kasus dan temuan juga mengirim array. Gunakan `limit` sampai 100 dan baca `X-Total-Count` untuk jumlah yang cocok dengan filter. Gunakan `X-Next-Cursor` sebagai `before` untuk job atau `after` untuk temuan. API portal mengirim `X-Total-Count`, `X-Failed-Count`, serta `X-Pending-Review-Count` bagi peran yang berhak meninjau temuan.

Badan impor berupa JSON berisi `content`, `column`, dan `format`. Gunakan `csv` untuk teks UTF-8, `xlsx` untuk file base64, dan `manual` untuk label manual yang diserialkan sebagai CSV oleh portal. Jika `format` tidak dikirim, API memakai CSV. Bukti dikirim sebagai lampiran byte dan menyertakan `X-Content-SHA256`.

## Gate A

Tes integrasi menjalankan impor, job sumber, review, dan dua laporan pada 20 Case ID fixture. Tes perangkat menjalankan hasil Android, unsupported, penolakan, pencabutan, dan putus koneksi di server simulasi. Gate A masih memerlukan desktop Tauri, antrean SQLite, protokol sinkronisasi dan telaah konflik, serta verifikasi skenario yang tersisa melalui desktop. Lihat [rencana Gate A](../task.md).
