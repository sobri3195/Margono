# Alur kasus sintetis lokal

Siapkan [PostgreSQL lokal](database.md) dan terapkan migrasi. Siapkan akun latihan dari terminal tepercaya di direktori `services/api`.

```bash
uv run --locked python -m margono_api.provision latihan-osint osint_analyst
uv run --locked python -m margono_api.provision latihan-supervisor supervisor
```

Pemberian akun melalui CLI ditujukan untuk pengembangan lokal. Gunakan kata sandi latihan unik minimal 12 karakter. Jalankan API dengan `MARGONO_DATABASE_URL` yang sama dan buka **Kasus simulasi tersimpan** di web. Masuk sebagai OSINT Analyst, pilih fixture, isi tujuan dan ruang lingkup, lalu buat kasus. Pilih CSV UTF-8 sintetis dan kolom label, tinjau baris, lalu konfirmasi. Kolom `Nama` dipilih secara default. Pratinjau menandai label kosong, lebar baris yang salah, dan duplikat. Duplikat tetap disimpan sebagai baris terpisah.

- Login menggunakan scrypt untuk kata sandi dan menyimpan hash token sesi acak di database. Sesi berlaku satu jam, diperiksa lagi pada setiap operasi, dan dapat dicabut lewat tombol **Keluar**. Token web berada di memori halaman.
- OSINT Analyst dan Forensic Examiner dapat membuat serta membaca kasus milik sendiri. Supervisor dapat membaca, menutup, dan membuka kembali kasus. Administrator tanpa peran kasus tidak mendapat akses bukti.
- OSINT Analyst dapat mengimpor CSV untuk kasus terbuka miliknya. Maksimum 64 KiB, 500 baris data, 100 kolom, dan 500 karakter per label valid. Kunci `Idempotency-Key` mengulang hasil konfirmasi yang identik. Isi atau kolom berbeda dengan kunci yang sama menghasilkan HTTP 409.
- Bukti impor menyimpan byte UTF-8 asli dan SHA-256. PostgreSQL menolak hash yang tidak sesuai serta pembaruan atau penghapusan biasa pada tabel bukti. Unduhan melalui API memeriksa hak akses dan menghitung ulang hash. Mutasi kasus, konfirmasi impor, dan siklus sesi mencatat peristiwa dan ID korelasi.
- Latihan menggunakan autentikasi lokal dengan kata sandi. Build masih menerapkan pembatasan mode lokal pada [kesiapan pilot](pilot-readiness.md).

## API

| Operasi | Endpoint |
| --- | --- |
| Login dan logout | `POST /api/v1/sessions` dan `DELETE /api/v1/sessions/current` |
| Buat dan daftar kasus | `POST /api/v1/cases` dan `GET /api/v1/cases` |
| Detail dan perubahan status Supervisor | `GET /api/v1/cases/{id}` dan `PATCH /api/v1/cases/{id}/status?status=closed` |
| Preview dan konfirmasi CSV | `POST /api/v1/cases/{id}/imports/preview` dan `POST /api/v1/cases/{id}/imports` |
| Unduh bukti | `GET /api/v1/cases/{id}/imports/{import_id}/evidence` |

Gunakan `Authorization: Bearer <token>` setelah login. Badan impor berupa JSON dengan teks CSV pada `content` dan nama kolom di `column`. Bukti dikirim sebagai lampiran byte dan menyertakan `X-Content-SHA256`.

## Gate A

Iterasi ini mencakup alur sintetis dari sesi lokal ke kasus dan bukti CSV. XLSX, adapter hasil dan review analis, workflow mock USB dan pembatalan berdasarkan consent, desktop Tauri, worker, antrean SQLite, sinkronisasi, serta dua laporan masih tercatat di [rencana Gate A](../task.md). Riwayat consent di database belum menjalankan alur pemeriksaan.
