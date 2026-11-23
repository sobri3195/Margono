# MARGONO

Prototipe lokal untuk membuka katalog kasus keamanan siber sintetis melalui workspace Web Intelligence dan USB Security. Semua data di layar berasal dari fixture. Prototipe hanya menyediakan operasi baca.

## Menjalankan prototipe

Gunakan Python 3.12 dengan [uv](https://docs.astral.sh/uv/) serta Node.js 24 dengan npm. Jalankan dua terminal dari root repositori.

```bash
cd services/api
uv sync --locked
uv run --locked uvicorn margono_api.main:app --host 127.0.0.1 --port 8000
```

```bash
cd apps/web
npm ci
npm run dev
```

Buka `http://127.0.0.1:5173`. Pilih **Web Intelligence** untuk melihat `SYN-001`. Pilih **USB Security** lalu pilih `SYN-012` untuk melihat profil iPhone dengan hasil **Tidak didukung**. OpenAPI tersedia pada `http://127.0.0.1:8000/openapi.json`.

## Validasi

```bash
(cd services/api && uv run --locked ruff check .)
(cd services/api && uv run --locked ruff format --check .)
(cd services/api && uv run --locked python -m pytest -q)
(cd apps/web && npm ci && npm run build)
```

## PostgreSQL untuk pengembangan

Lihat [panduan database](docs/database.md) untuk menjalankan PostgreSQL lokal, menerapkan migrasi, dan menguji constraint pada database terpisah.

## Dokumen

- [PRD](prd.md) mencatat persyaratan dan kriteria penerimaan.
- [Rencana pengerjaan](task.md) mencatat status tugas dan target pengujian.
- [Catatan keputusan](brainstorming.md) mencatat pilihan awal serta keputusan terbuka.
- [Batas sistem dan kontrak API](docs/simulation.md) menjelaskan aliran data, model ancaman awal, dan batas prototipe.
