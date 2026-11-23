# PostgreSQL untuk pengembangan

Migrasi Alembic membuat skema operasional awal di PostgreSQL 17. Gunakan database pengembangan lokal dan data sintetis. Katalog simulasi tetap dapat dijalankan tanpa koneksi database.

## Migrasi lokal

Jalankan dari root repositori. Gunakan kembali kredensial lokal yang sama selama volume Compose dipakai.

```bash
export MARGONO_POSTGRES_PASSWORD="$(openssl rand -hex 18)"
export MARGONO_POSTGRES_PORT=5432
export MARGONO_DATABASE_URL="postgresql+psycopg://margono:${MARGONO_POSTGRES_PASSWORD}@127.0.0.1:${MARGONO_POSTGRES_PORT}/margono"
docker compose -f infra/local/compose.yaml up -d --wait
(cd services/api && uv run --locked alembic upgrade head)
(cd services/api && uv run --locked alembic current)
```

Port dipublikasikan pada `127.0.0.1`. Jika port sudah dipakai, tetapkan `MARGONO_POSTGRES_PORT` sebelum menjalankan Compose. `docker compose -f infra/local/compose.yaml down` menghentikan layanan dan mempertahankan volume. `alembic downgrade base` menghapus tabel operasional beserta datanya dan digunakan hanya pada database uji yang dapat dibuang.

Revisi Alembic ditulis secara eksplisit. Proyek belum memiliki metadata ORM untuk `alembic check` atau autogenerate.

## Tes integrasi

Buat database tes satu kali pada instance lokal terisolasi. Setiap tes menggunakan skema sementara sendiri dan menghapus skema itu setelah selesai. Jalan cepat `pytest` tanpa URL hanya menjalankan tes API.

```bash
docker compose -f infra/local/compose.yaml exec -T postgres createdb -U margono margono_test
export MARGONO_TEST_DATABASE_URL="${MARGONO_DATABASE_URL%/*}/margono_test"
(cd services/api && uv run --locked python -m pytest -q)
```

## Cakupan skema

- `users`, `roles`, dan `user_roles` menyimpan akun dan empat peran awal beserta relasinya. Migrasi mengisi peran tanpa membuat akun.
- `cases` menyimpan pemilik, tujuan, cakupan, dan status. `device_sessions` dan `consent_records` menyimpan relasi sesi, cakupan consent, disclosure, keputusan, dan waktu pencabutan.
- `imports` dan `import_rows` mempertahankan posisi impor dan label referensi. Dua baris dapat memiliki label yang sama.
- `jobs` menjaga keunikan kunci idempotensi per kasus dan jenis job. `audit_events` menyimpan metadata peristiwa, termasuk ID korelasi jika tersedia. Kolom waktu menggunakan tipe PostgreSQL `timestamptz`.

PR skema belum menyediakan autentikasi, penegakan RBAC, pemrosesan antrean, penghentian job ketika consent dicabut, atau audit bertanda tangan. API simulasi tetap baca-saja dan tidak membuka akses ke tabel ini.
