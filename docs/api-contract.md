# Kontrak HTTP v1

Endpoint katalog simulasi menyediakan JSON melalui `GET` pada `/api/v1`. Operasi persisten dengan sesi operator dijelaskan di [alur kasus sintetis](synthetic-cases.md). Skema yang berlaku tersedia di `/openapi.json`. Gunakan fixture sesuai [batas penggunaan](acceptable-use.md).

| Endpoint | Hasil |
| --- | --- |
| `GET /api/v1/health` | Liveness proses API. `{"status":"ok","mode":"SYNTHETIC"}` |
| `GET /api/v1/readiness` | Status operasional PostgreSQL, worker, sinkronisasi, dan pilot. Build simulasi mengembalikan `503 not_ready` dengan status tiap komponen. |
| `GET /api/v1/simulation/catalog` | Kasus, profil sumber, dan profil perangkat sintetis. |
| `GET /api/v1/simulation/cases/{case_id}` | Satu kasus sintetis. ID yang tidak dikenal menghasilkan `404 case_not_found`. |
| `GET /api/v1/simulation/plans?seed=42` | Tiga Case ID dari setiap workspace. Seed berupa bilangan bulat bertanda 32-bit. Parameter query tambahan menghasilkan `422 invalid_request`. Permintaan dengan seed yang sama menghasilkan urutan yang sama selama katalog dan algoritme tetap sama. |

## Contoh respons

Permintaan `GET /api/v1/simulation/plans?seed=42` menghasilkan HTTP 200 dan header `X-Correlation-ID` berupa UUID versi 4. Server membuat ID baru saat permintaan masuk, termasuk jika klien mengirim header bernama sama.

```json
{
  "mode": "SYNTHETIC",
  "seed": 42,
  "case_ids": ["SYN-016", "SYN-002", "SYN-001", "SYN-018", "SYN-013", "SYN-012"]
}
```

Detail `SYN-001` dan entri yang sama di katalog memiliki `created_at` bernilai `2026-01-01T00:00:00Z`. Timestamp fixture konsisten lintas permintaan. Timestamp JSON memakai RFC 3339 dalam UTC dengan akhiran `Z`.

Permintaan `GET /api/v1/simulation/plans?seed=abc` menghasilkan HTTP 422 dan header korelasi baru.

```json
{"code":"invalid_request","message":"Request parameters are invalid."}
```

Klien menangani kegagalan berdasarkan status HTTP dan `code`. `message` ditujukan untuk tampilan. Format kesalahan yang sama dipakai untuk `404 not_found`, `404 case_not_found`, `405 method_not_allowed`, serta `500 internal_error`. Respons 405 menyertakan `Allow`. Detail input yang ditolak dan detail pengecualian internal tidak disertakan di respons.

## Idempotensi operasi tulis mendatang

Endpoint simulasi saat ini bersifat baca-saja. Konvensi berikut berlaku saat endpoint tulis yang mendukung percobaan ulang ditambahkan.

- `Idempotency-Key` wajib pada endpoint yang mendeklarasikannya. Nilainya 1–128 karakter ASCII dari `A–Z`, `a–z`, `0–9`, `.`, `_`, `:`, atau `-`. Kunci hilang atau tidak valid menghasilkan `422 invalid_request`.
- Server memeriksa otorisasi sebelum membaca hasil lama. Ruang lingkup kunci mengikuti operasi dan resource yang dicantumkan pada endpoint. Job kasus menggunakan kombinasi Case ID, jenis job, dan kunci.
- Server menyimpan fingerprint permintaan dan hasil secara atomik. Pengulangan dengan payload yang sama mengembalikan status dan body asli serta ID korelasi baru. Payload berbeda pada kunci yang sama menghasilkan `409 idempotency_conflict`. Jika permintaan awal masih berjalan, kembalikan `409 idempotency_in_progress` agar klien dapat mencoba ulang dengan kunci sama.
- Dokumentasi tiap endpoint akan menetapkan masa berlaku kunci sebelum operasi diaktifkan.

Contoh kontrak untuk pengajuan job sintetis di masa mendatang.

```http
POST /api/v1/cases/4e4d0207-adb9-4407-8150-fbca2b4f6824/jobs
Content-Type: application/json
Idempotency-Key: fixture-job-001

{"kind":"source_review"}
```

Jika pengajuan pertama menghasilkan HTTP 202, percobaan ulang identik mengembalikan HTTP 202 dan Job ID yang sama dengan contoh di bawah.

```json
{"job_id":"a37df074-3a3b-4113-bac0-66fd933f9859","status":"queued"}
```
