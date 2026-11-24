# Alur kasus sintetis lokal

Siapkan [PostgreSQL lokal](database.md) dan terapkan migrasi. Siapkan akun latihan dari terminal tepercaya di direktori `services/api`.

```bash
uv run --locked python -m margono_api.provision latihan-osint osint_analyst
uv run --locked python -m margono_api.provision latihan-supervisor supervisor
```

Pemberian akun melalui CLI ditujukan untuk pengembangan lokal. Gunakan kata sandi latihan unik minimal 12 karakter. Jalankan API dengan `MARGONO_DATABASE_URL` yang sama dan buka **Kasus simulasi tersimpan** di web. Masuk sebagai OSINT Analyst, pilih fixture, isi tujuan dan ruang lingkup, lalu buat kasus. Pilih CSV UTF-8 sintetis dan kolom label, tinjau baris, lalu konfirmasi. Pilih kolom dari header CSV yang dibaca API. Kolom `Nama` menjadi pilihan awal jika tersedia. Pratinjau menandai label kosong, lebar baris yang salah, dan duplikat. Duplikat tetap disimpan sebagai baris terpisah. Pratinjau dan konfirmasi terikat ke Case ID asal. Berpindah kasus membuang pratinjau lokal dan mengabaikan respons lama.

Panel **Riwayat impor** menampilkan waktu, kolom yang dipilih, jumlah baris valid, tidak valid, atau menunggu, dan SHA-256 jika tersedia. Bukti bisa diunduh oleh operator yang dapat membaca kasus. Riwayat dimuat per halaman dan tetap menampilkan catatan lama tanpa bukti.

- Login menggunakan scrypt untuk kata sandi dan menyimpan hash token sesi acak di database. Sesi berlaku satu jam, diperiksa lagi pada setiap operasi, dan dapat dicabut lewat tombol **Keluar**. Token web berada di memori halaman.
- OSINT Analyst dan Forensic Examiner dapat membuat serta membaca kasus milik sendiri. Supervisor dapat membaca, menutup, dan membuka kembali kasus. Administrator tanpa peran kasus tidak mendapat akses bukti.
- OSINT Analyst dapat mengimpor CSV untuk kasus terbuka miliknya. Maksimum 64 KiB, 500 baris data, 100 kolom, dan 500 karakter per label valid. Kunci `Idempotency-Key` mengulang hasil konfirmasi yang identik. Isi atau kolom berbeda dengan kunci yang sama menghasilkan HTTP 409.
- Bukti impor menyimpan byte UTF-8 asli dan SHA-256. PostgreSQL menolak hash yang tidak sesuai serta pembaruan atau penghapusan biasa pada tabel bukti. Unduhan melalui API memeriksa hak akses dan menghitung ulang hash. Mutasi kasus, konfirmasi impor, dan siklus sesi mencatat peristiwa dan ID korelasi. Konfirmasi dan penyajian bukti yang lolos verifikasi mencatat Case ID, Import ID, actor dan ID korelasi. Peristiwa penyajian mencatat keputusan server mengirim bukti. Pengiriman byte hingga selesai dan persetujuan rilis formal memerlukan kontrol tersendiri.
- Latihan menggunakan autentikasi lokal dengan kata sandi. Build masih menerapkan pembatasan mode lokal pada [kesiapan pilot](pilot-readiness.md).

## API

| Operasi | Endpoint |
| --- | --- |
| Login dan logout | `POST /api/v1/sessions` dan `DELETE /api/v1/sessions/current` |
| Buat dan daftar kasus | `POST /api/v1/cases` dan `GET /api/v1/cases` dengan `before` dan `limit` opsional |
| Detail dan perubahan status Supervisor | `GET /api/v1/cases/{id}` dan `PATCH /api/v1/cases/{id}/status?status=closed` |
| Daftar header CSV | `POST /api/v1/cases/{id}/imports/columns` |
| Riwayat impor | `GET /api/v1/cases/{id}/imports` dengan paginasi opsional `before` dan `limit` |
| Preview dan konfirmasi CSV | `POST /api/v1/cases/{id}/imports/preview` dan `POST /api/v1/cases/{id}/imports` |
| Unduh bukti | `GET /api/v1/cases/{id}/imports/{import_id}/evidence` |

Gunakan `Authorization: Bearer <token>` setelah login. Untuk membuat kasus, web mengirim `Idempotency-Key` baru dan memakai kunci yang sama saat mencoba ulang payload yang sama. Klien API lama tetap bisa membuat kasus tanpa header tersebut. Jika kunci dikirim, percobaan ulang oleh operator yang sama mengembalikan `201` dan respons asli, termasuk setelah kasus ditutup. Perubahan payload dengan kunci yang sama menghasilkan `409 idempotency_conflict`. Tujuan dan ruang lingkup dengan karakter kontrol menghasilkan `422` sebelum transaksi.

Daftar kasus tetap mengirim array. Jika halaman berikutnya tersedia, gunakan nilai header `X-Next-Cursor` sebagai parameter `before`. Tombol **Muat kasus sebelumnya** mengikuti cursor itu dan mempertahankan pilihan saat ini.

Badan impor berupa JSON dengan teks CSV pada `content` dan nama kolom di `column`. Bukti dikirim sebagai lampiran byte dan menyertakan `X-Content-SHA256`.

## Gate A

Iterasi ini mencakup alur sintetis dari sesi lokal ke kasus dan bukti CSV. XLSX, adapter hasil dan review analis, workflow mock USB dan pembatalan berdasarkan consent, desktop Tauri, worker, antrean SQLite, sinkronisasi, serta dua laporan masih tercatat di [rencana Gate A](../task.md). Riwayat consent di database belum menjalankan alur pemeriksaan.
