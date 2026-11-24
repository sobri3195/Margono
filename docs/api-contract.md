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

## Idempotensi operasi tulis

Endpoint katalog simulasi bersifat baca-saja. Konfirmasi impor memakai kunci wajib. Pembuatan kasus mendukung kunci opsional untuk kompatibilitas klien, dan web selalu mengirim kunci. Aturan berikut berlaku untuk endpoint tulis yang mendeklarasikan idempotensi.

- Endpoint menetapkan apakah `Idempotency-Key` wajib atau opsional. Nilainya 1–128 karakter ASCII dari `A–Z`, `a–z`, `0–9`, `.`, `_`, `:`, atau `-`. Kunci wajib yang hilang atau kunci yang tidak valid menghasilkan `422 invalid_request`.
- Server memeriksa otorisasi sebelum membaca hasil lama. Ruang lingkup kunci mengikuti operasi dan resource yang dicantumkan pada endpoint. Pembuatan kasus memakai pasangan operator dan kunci. Konfirmasi impor memakai pasangan Case ID dan kunci. Job sumber memakai Case ID, jenis job, dan kunci. Sesi perangkat memakai Case ID dan kunci keputusan. Job perangkat hanya dibuat sekali per sesi.
- Server menyimpan fingerprint permintaan dan hasil secara atomik. Pengulangan dengan payload yang sama mengembalikan ID resource yang sama dan ID korelasi baru. Pembuatan kasus dan konfirmasi impor mengembalikan body asli. Job dan sesi perangkat mengembalikan status resource saat ini. Payload berbeda pada kunci yang sama menghasilkan `409 idempotency_conflict`. Permintaan simultan untuk pembuatan kasus dan konfirmasi impor diserialisasi di database. Retry membaca hasil setelah transaksi awal selesai.
- Untuk simulasi lokal, receipt pembuatan kasus dan kunci konfirmasi mengikuti umur data pada database. Kebijakan kedaluwarsa produksi masih perlu ditetapkan.

`GET /api/v1/cases/creation-receipt` mengembalikan keadaan kasus terbaru yang dibuat dengan kunci tersebut oleh operator. `GET /api/v1/cases/{case_id}/imports/confirmation` mengembalikan hasil konfirmasi milik operator dari riwayat kasus, terlepas dari halaman daftar riwayat. Kedua operasi meminta header `Idempotency-Key` dan sesi yang berwenang. Jika hasil belum tersimpan, responsnya `200` dengan badan JSON `null`.

Contoh pengajuan job sumber sintetis untuk batch yang sudah tersimpan.

```http
POST /api/v1/cases/4e4d0207-adb9-4407-8150-fbca2b4f6824/imports/33034875-9e85-4d9b-abcd-956c4f6391fe/jobs
Authorization: Bearer <token>
Idempotency-Key: fixture-job-001
```

Percobaan pertama dan ulang mengembalikan HTTP 201 dan Job ID yang sama pada field `id`.
