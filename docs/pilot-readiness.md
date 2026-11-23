# Kesiapan operasional dan pilot

Build ini beroperasi dalam mode `simulation`, baik jika `MARGONO_MODE` belum ditetapkan maupun jika nilainya `simulation`. Startup dengan nilai lain, termasuk `pilot` dan `production`, gagal. Katalog demo dan API baca-saja bisa berjalan dengan fixture sintetis tanpa database.

## Memeriksa layanan

- `/api/v1/health` memeriksa liveness proses API. Gunakan endpoint ini untuk memantau proses katalog simulasi.
- `/api/v1/readiness` melaporkan kesiapan operasional dengan `Cache-Control: no-store`. `database` bernilai `not_configured` jika URL belum disediakan, `unavailable` jika konfigurasi atau koneksi gagal, `migration_required` jika revisi database berbeda dari head Alembic, atau `ready` jika revisi sesuai. Atur `MARGONO_DATABASE_URL` dan jalankan migrasi sesuai [panduan database](database.md).
- Worker dan sinkronisasi dilaporkan sebagai `not_implemented`. Endpoint mengembalikan HTTP 503 dengan `status: not_ready` dan `pilot: blocked`, termasuk ketika PostgreSQL siap. Panel web menampilkan hasil per komponen dan katalog tetap dapat dipakai.
- Untuk kegagalan katalog, salin `X-Correlation-ID` jika ditampilkan dan gunakan **Coba lagi**. Permintaan katalog yang masih menunggu setelah 10 detik dihentikan. ID mungkin belum tersedia jika respons belum mengirim header. Log status API dapat dicari berdasarkan ID tersebut dan tidak mencantumkan nilai query pada pesan status.

## Bukti yang diperlukan sebelum membuka pilot

| Area | Prasyarat dan bukti |
| --- | --- |
| Identitas dan akses | Login internal dan RBAC tersedia. Verifikasi MFA, pemulihan akun yang diaudit, dan penolakan akses lintas kasus. |
| Perangkat dan offline | Desktop Windows tersedia. Uji enrollment, mTLS dan revokasi di gateway, batas offline 8 jam, serta SQLCipher dan penyimpanan kunci Windows di perangkat uji. |
| Bukti dan pemulihan | Pilih KMS dan penyimpanan WORM di private cloud. Uji verifikasi manifest bertanda tangan, integritas audit, pemulihan ke titik waktu, dan pemulihan bukti. |
| Retensi dan ekspor | Tetapkan aturan retensi dan otorisasi Supervisor. Uji legal hold, penolakan ekspor tanpa izin, dan audit persetujuan. |
| Sumber dan perangkat nyata | Gunakan konektor resmi yang disetujui dan perangkat uji dengan persetujuan spesifik yang dapat dicabut. Catat kapabilitas, keterbatasan, dan hasil pengujian. |
| Keputusan Go/No-Go | Lampirkan hasil Gate B, peninjauan independen, dan persetujuan tertulis Supervisor sebelum pilot. |

Daftar di atas mengikuti [Gate B dan C](../prd.md#11-mvp-acceptance-criteria-and-release-gates). Status database di endpoint readiness hanya mengukur koneksi dan revisi. Bukti kontrol pilot dikumpulkan lewat pengujian dan persetujuan yang terdokumentasi.
