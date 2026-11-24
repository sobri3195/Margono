# Pemeriksaan pengembangan

## CI dan browser

Workflow CI menjalankan Ruff, tes API dan PostgreSQL, build web, serta regresi Chromium. Job `secrets` memindai riwayat Git yang di-checkout dengan Gitleaks versi tetap. Skrip memverifikasi SHA-256 distribusi dan menyamarkan kecocokan sebelum mencetaknya. Untuk menjalankan scan yang sama di Linux x64, gunakan `bash scripts/scan-secrets.sh` dari root repositori.

Regresi browser meliputi respons katalog yang rusak, timeout, tema, keyboard, batas kontras kontrol, axe-core, tautan kasus, serta akses ke tautan kasus tersimpan. Pemeriksaan otomatis mencakup semantik yang terlihat oleh browser pada tampilan desktop. Uji manual dengan screen reader dan aplikasi desktop Tauri masih terbuka.

## Benchmark impor sintetis

Siapkan PostgreSQL tes sesuai [panduan database](database.md). Jalankan dari root repo.

```bash
(cd services/api && uv run --locked python -m pytest -q -s tests/benchmark_import.py)
```

Benchmark membuat skema tes sementara. Setiap batch memiliki 500 baris sintetis dengan label berulang. Setelah tiga pemanasan, harness mencatat 25 sampel berurutan per tahap. p50 adalah median dan p95 menggunakan metode nearest-rank. Pengukuran mencakup aplikasi ASGI dan koneksi PostgreSQL 17 lokal. Hasil berikut merupakan satu pengukuran di Codex Cloud.

| Tahap | p50 | p95 |
| --- | ---: | ---: |
| Pratinjau CSV | 19,65 ms | 23,31 ms |
| Konfirmasi dan simpan bukti | 58,09 ms | 66,78 ms |
| Replay idempoten | 22,77 ms | 31,81 ms |

Angka ini belum mencakup jaringan pengguna, konkurensi, worker, review, atau laporan. Tambahkan pengukuran job, review, dan laporan saat alurnya tersedia.
