# Pemeriksaan pengembangan

## CI dan browser

Workflow CI menjalankan Ruff, tes API dan PostgreSQL, build web, serta regresi Chromium. Job `secrets` memindai riwayat Git yang di-checkout dengan Gitleaks versi tetap. Skrip memverifikasi SHA-256 distribusi dan menyamarkan kecocokan sebelum mencetaknya. Untuk menjalankan scan yang sama di Linux x64, gunakan `bash scripts/scan-secrets.sh` dari root repositori. Workflow hasil pembaruan ini lulus di main pada [run 45411639371](https://github.com/sobri3195/Margono/actions/runs/45411639371).

Regresi browser meliputi respons katalog yang rusak, timeout, tema, keyboard, batas kontras kontrol, axe-core, tautan kasus, serta akses ke tautan kasus tersimpan. Pemeriksaan hasil pembuatan kasus dan konfirmasi impor dapat diaktifkan dengan keyboard. Tes juga memeriksa teks status, deskripsi aksesibel tombol, dan penggunaan endpoint baca-saja. Uji manual dengan screen reader dan aplikasi desktop Tauri masih terbuka.

## Benchmark alur kasus sintetis

Siapkan PostgreSQL tes sesuai [panduan database](database.md). Jalankan dari root repo.

```bash
(cd services/api && uv run --locked python -m pytest -q -s tests/benchmark_import.py)
```

Benchmark membuat skema tes sementara untuk setiap skenario. Setiap batch memiliki 500 baris sintetis dengan label berulang. Setelah tiga pemanasan, harness mencatat 25 sampel per tahap. p50 adalah median dan p95 menggunakan metode nearest-rank. Pengukuran permintaan mencakup aplikasi ASGI dan koneksi PostgreSQL lokal hingga body respons tersedia. Laju mengukur jumlah operasi per detik sepanjang tahap, termasuk penjadwalan klien.

Berikut hasil satu kali pengukuran di Codex Cloud dengan kuota 4 CPU, Python 3.12.14, PostgreSQL 17.12, dan Procrastinate 3.12.0.

### Impor berurutan

| Tahap | p50 | p95 |
| --- | ---: | ---: |
| Pratinjau CSV | 22,21 ms | 29,63 ms |
| Konfirmasi dan simpan bukti | 61,42 ms | 76,92 ms |
| Replay idempoten | 26,83 ms | 29,92 ms |

### Empat klien paralel

Harness menjalankan setiap tahap secara terpisah dengan hingga empat permintaan paralel. Skenario pertama mengimpor 25 batch ke 25 kasus. Skenario kedua mengimpor 25 batch ke satu kasus. Laporan masing-masing kasus memuat satu temuan pada skenario pertama dan 25 temuan pada skenario kedua.

| Tahap | 25 kasus p50/p95 | Operasi/detik | Satu kasus p50/p95 | Operasi/detik |
| --- | ---: | ---: | ---: | ---: |
| Pratinjau | 58,32/82,14 ms | 64,70 | 57,86/71,56 ms | 66,59 |
| Konfirmasi | 213,31/343,37 ms | 17,38 | 195,95/279,09 ms | 18,38 |
| Replay | 52,68/193,67 ms | 54,35 | 53,86/66,06 ms | 71,14 |
| Tambah job ke antrean | 75,53/106,35 ms | 48,40 | 102,87/166,14 ms | 35,21 |
| Simpan keputusan review | 63,02/96,14 ms | 59,25 | 65,88/90,28 ms | 57,50 |
| Laporan eksekutif | 57,32/128,06 ms | 58,90 | 50,55/70,93 ms | 71,32 |
| Laporan teknis | 57,27/73,47 ms | 66,53 | 67,88/92,73 ms | 56,98 |

| Worker Procrastinate | 25 kasus | Satu kasus |
| --- | ---: | ---: |
| Eksekusi job p50/p95 | 25,89/30,99 ms | 27,56/39,60 ms |
| Sejak masuk antrean hingga selesai p50/p95 | 726,60/839,57 ms | 927,36/972,88 ms |
| Laju pengosongan antrean | 30,49 job/detik | 28,50 job/detik |
| Retry job | 0 | 0 |

Satu worker dijalankan setelah seluruh job dalam skenario masuk antrean. Durasi eksekusi dihitung dari event mulai hingga sukses di PostgreSQL. Durasi antrean hingga selesai juga mencakup waktu mengumpulkan batch dan startup worker. Beban ini memakai fixture sukses dan mengukur aplikasi serta database lokal. Pengukuran jaringan pengguna, perangkat desktop, dan beban berkepanjangan masih terbuka.
