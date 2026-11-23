# MARGONO - Brainstorming dan Decision Log

**Versi:** 1.0  
**Tanggal konsolidasi:** 23 November 2026  
**Status:** Ringkasan keputusan diskusi; belum merupakan izin operasional atau persetujuan keamanan.  
**Dokumen turunan:** `prd.md`, `task.md`, `codex_prompt.md`

## 1. Identitas proyek

**Nama:** MARGONO  
**Ekspansi nama sementara:** **M**ilitary **A**ssessment of **R**isk, **G**overnance, **O**nline **N**etworks & **O**perations.  
**Positioning:** Integrated Military Cybersecurity & Digital Evidence Platform.

**Pengguna utama:** Tim siber dan forensik digital militer.  
**Model pengembangan:** Satu pengembang dengan bantuan AI.  
**Target kerja:** 6 bulan, dikendalikan oleh kelulusan milestone, bukan tenggat yang menjamin kemampuan forensik tertentu.

### 1.1 Tujuan yang disepakati untuk produk

- Mendeteksi indikator ancaman keamanan siber yang objektif: paparan informasi kedinasan, impersonasi institusi, domain/URL/IOC berbahaya, dan kelemahan keamanan perangkat yang diotorisasi.
- Mengelola investigasi secara terpadu melalui dua workspace: Web Intelligence dan USB Security Diagnostics.
- Menjaga integritas temuan, provenance, audit akses, dan laporan teknis serta eksekutif.
- Melakukan pemeriksaan HP pribadi hanya berdasarkan persetujuan spesifik, sukarela, terdokumentasi, dan dapat dicabut.

### 1.2 Batas keselamatan, privasi, dan penggunaan

Ide awal diskusi mencakup upaya menyimpulkan kecenderungan LGBT dari nama, media sosial, atau HP. **Kemampuan itu tidak masuk ruang lingkup dan tidak boleh dikembangkan.** MARGONO tidak melakukan penentuan atau prediksi orientasi seksual, identitas gender, hubungan personal, atau karakteristik sensitif; tidak membuat skor personel berbasis karakteristik tersebut. Tidak ada mekanisme otomatis untuk menyimpulkan kelayakan personel.

Untuk mencegah pengaitan identitas yang keliru, input `Nama` dipakai sebagai label referensi kasus yang ditinjau manusia, **bukan** sebagai dasar tunggal untuk mengaitkan akun media sosial dengan seseorang. Pencarian otomatis dibatasi pada indikator ancaman keamanan publik yang jelas dan/atau target organisasi yang terotorisasi. Tidak ada enumerasi massal akun personal berdasarkan daftar nama. Konten pribadi HP, termasuk pesan, foto, kontak, riwayat peramban, dan aplikasi personal yang tidak relevan, tidak diambil.

## 2. Ringkasan arsitektur terpilih

```text
                          MARGONO PRIVATE CLOUD
              +-----------------------------------------+
              | FastAPI API + Auth/MFA + RBAC           |
              | PostgreSQL + Procrastinate Worker      |
              | Case Management + Evidence Metadata    |
              | KMS + WORM Audit Archive               |
              | Threat Intelligence Updates            |
              +----------------+------------------------+
                               ^
                      TLS 1.3 + mTLS
                               v
        +----------------------+---------------------+
        |                                            |
  WEB INTELLIGENCE                              WINDOWS DESKTOP
  React + Vite                                  Tauri + React + Rust
  XLSX/CSV Guided Wizard                       Android / iPhone
  Public cyber threat sources                  Local SQLCipher/SQLite queue
  Analyst verification                         Security metadata + scoped IOC
        |                                            |
        +----------------------+---------------------+
                               v
                 Unified Case + Evidence + Reports
```

Catatan teknis: dukungan USB Android dan iPhone berbeda. Tidak boleh mengklaim full-file-system access, deteksi semua spyware, atau kemampuan pemindaian iPhone yang tidak tersedia melalui antarmuka resmi dan izin yang sah.

## 3. Keputusan yang sudah ditetapkan

### 3.1 Misi, pengguna, dan ruang kerja

| ID | Area | Keputusan |
|---|---|---|
| D-01 | Pengguna utama | Tim siber dan forensik digital militer. |
| D-02 | Fitur | Dua modul terpadu sejak awal: Web Intelligence dan USB Security. |
| D-03 | Indikator | Paparan informasi dinas, impersonasi institusi, dan ancaman keamanan HP. |
| D-04 | Input identitas | Nama saja, verifikasi manual; nama bukan identitas terkonfirmasi. |
| D-05 | Sumber | Mesin pencari, situs publik, kanal sosial publik yang relevan dengan ancaman institusi, dan threat-intel berlisensi/API resmi. |
| D-06 | Hasil | Tabel batch + investigasi kasus + laporan terpadu. |
| D-07 | HP | HP pribadi dengan persetujuan spesifik dan sukarela. |
| D-08 | OS mobile | Android dan iPhone; batas kemampuan setiap platform diungkap. |
| D-09 | Operasi | Hybrid offline-online; analisis lokal, sinkronisasi terbatas. |

### 3.2 Stack, deployment, akses

| ID | Area | Keputusan |
|---|---|---|
| D-10 | Desktop | Tauri + React + Vite + Rust, distribusi Windows EXE. |
| D-11 | Backend | Python + FastAPI. |
| D-12 | Database | PostgreSQL terpusat dan SQLite lokal (terenkripsi dengan SQLCipher). |
| D-13 | Hosting | Private Cloud. |
| D-14 | Login | Akun internal dengan MFA. |
| D-15 | RBAC | Standard RBAC: Administrator, OSINT Analyst, Forensic Examiner, Supervisor. |
| D-16 | Struktur | Unified Case + Digital Evidence, Case ID, SHA-256, chain of custody, catatan persetujuan. |
| D-17 | Retensi | Policy-Based Retention menurut kategori data dan kewajiban yang sah. |
| D-18 | Penghapusan | Hybrid Evidence Lifecycle: hapus operasional menurut kebijakan; legal hold untuk bukti yang wajib disimpan. |
| D-19 | DR | Advanced Disaster Recovery: PostgreSQL PITR, backup terisolasi, uji pemulihan. |

### 3.3 Pengembangan, validasi, dan rilis

| ID | Area | Keputusan |
|---|---|---|
| D-20 | Validasi | Staged Validation: data sintetis lalu pilot terbatas yang sah. |
| D-21 | KPI primer | Integrasi end-to-end. |
| D-22 | Skala simulasi | 20 kasus sintetis, 2 perangkat uji (1 Android, 1 iPhone). |
| D-23 | Performa | Benchmark First, tidak menjanjikan SLA scanning tanpa data. |
| D-24 | Gate | Comprehensive Security Validation. |
| D-25 | Roadmap | 4 tahap: Prototype, Security Validation, Controlled Pilot, Operational Readiness. |
| D-26 | Durasi | Target 6 bulan. |
| D-27 | Tim | Solo developer dengan AI; audit keamanan independen sebelum pilot. |
| D-28 | Strategi | Simulation-First Integration. |
| D-29 | Simulator | Hybrid: 20 kasus tetap + skenario dinamis deterministik (seed). |
| D-30 | Test gate | OSINT, USB, evidence integrity, dan security wajib diuji. |
| D-31 | Lulus | Seluruh kontrol kritis dan 20 alur inti harus lulus; ambang nonkritis berbasis benchmark. |
| D-32 | Go/No-Go | Supervisor Approval; tidak menggantikan kewajiban hukum atau otorisasi pemeriksaan. |

### 3.4 Mesin deteksi, pelaporan, dan pengalaman pengguna

| ID | Area | Keputusan |
|---|---|---|
| D-33 | Cakupan USB pilot | Security metadata + threat detection, tanpa mengakses konten pribadi. |
| D-34 | Threat intel | Hybrid: database lokal, update bertanda tangan digital, verifikasi tambahan saat online. |
| D-35 | Analisis | Tiered Threat Analysis: signature, multi-source correlation, review analis. |
| D-36 | Status | Confirmed, Suspected, Inconclusive, False Positive - hanya untuk ancaman teknis. |
| D-37 | Insiden | Tiered Incident Reporting: severity, verifikasi, alert kritis, Supervisor review. |
| D-38 | Laporan | Dual-Report: Executive dan Technical Forensic dari Case ID yang sama. |
| D-39 | Tema | Adaptive Dual Theme: dark + light. |
| D-40 | Navigasi | Dual Workspace Navigation: Web Intelligence / USB Forensics. |
| D-41 | Landing | Workspace Selection Portal. |
| D-42 | Portal | Operational Portal: status sistem, sinkronisasi, notifikasi tugas. |
| D-43 | Import | Guided Scanning Wizard. |
| D-44 | Format | Smart Column Mapping, XLSX/CSV fleksibel, validasi awal. |
| D-45 | Duplikasi | Smart Duplicate Review, tak menggabungkan orang tanpa verifikasi. |
| D-46 | Review OSINT | Evidence-Based Verification dengan checklist sumber, waktu, relevansi, dan bukti. |
| D-47 | Tidak terverifikasi | Hybrid Verification Lifecycle: arsip terbatas, re-review sah, retensi/penghapusan. |
| D-48 | Monitor | Advanced Monitoring: log, status API, antrean, Pause/Resume/Cancel/Retry. |

### 3.5 Antrean, sinkronisasi, dan proteksi data

| ID | Area | Keputusan |
|---|---|---|
| D-49 | Job model | Intelligent Durable Queue: persistent, checkpoints, retry terbatas, idempotent. |
| D-50 | Queue tech | Procrastinate + PostgreSQL (server), SQLite (lokal). |
| D-51 | Sinkronisasi | Evidence-First: immutable original, append-only versions, conflict review. |
| D-52 | Enkripsi | SQLCipher, Windows secure key storage, TLS 1.3, Private Cloud KMS, rotasi kunci. |
| D-53 | Laptop security | Advanced Device Protection: token revoke, lock, alert, audit. |
| D-54 | Offline | Sesi offline maksimal 8 jam setelah login MFA online. |
| D-55 | Key recovery | Managed Key Recovery melalui KMS, Supervisor authorization, audit. |
| D-56 | Key lifecycle | Hybrid Key Lifecycle: rotasi terjadwal dan darurat, key versions, revocation. |
| D-57 | Trust | Sertifikat perangkat unik + mTLS. |
| D-58 | Enrollment | Undangan sekali pakai, kunci lokal, persetujuan Administrator. |
| D-59 | Sertifikat | Risk-adaptive, berlaku maksimal 90 hari, pembaruan bersyarat, revocation online. |
| D-60 | Migrasi | Hybrid Secure Migration dari cloud dan data offline terenkripsi jika tersedia. |
| D-61 | Pemulihan | Signed evidence manifest, SHA-256, discrepancy report, quarantine, Supervisor, audit. |
| D-62 | Audit storage | Hash chaining, signature, WORM archive. |
| D-63 | Audit monitoring | Verifikasi berkala + event-driven tamper detection + Supervisor alerts. |
| D-64 | Notifikasi | Dashboard + desktop + email kedinasan + eskalasi internal terotorisasi. |

### 3.6 Belum diputuskan

- **Incident Response SLA (pertanyaan ke-65):** fixed, risk-adaptive, atau manual. Jangan menganggap pilihan default UI sebagai keputusan final.
- Private Cloud provider, region, klasifikasi data yang diizinkan, model isolasi jaringan, dan mekanisme KMS/WORM yang tersedia.
- Versi minimum Windows/Android/iOS dan metode mobile security diagnostics yang benar-benar didukung.
- Kebijakan masa retensi spesifik per kategori, prosedur legal hold, serta pihak yang berwenang menetapkannya.
- Data katalog target institusi, izin konektor eksternal, API credentials, dan batas ToS masing-masing sumber.
- Format/templating final untuk dua laporan, skema klasifikasi dokumen, masa berlaku undangan enrollment.
- Definisi deteksi 'Critical' dan SLA acknowledgment serta tindak lanjut.

## 4. Alur operasional kandidat

### 4.1 Web Intelligence

1. Petugas MFA login dan memilih Web Intelligence.
2. Membuat atau memilih Case ID dengan justifikasi ancaman keamanan yang spesifik.
3. Mengunggah XLSX/CSV; memilih kolom `Nama` (label kasus); preview dan validasi.
4. Meninjau duplikat; tidak menggabungkan identitas otomatis.
5. Memilih sumber keamanan publik yang sah dan ruang lingkup pencarian yang relevan dengan organisasi/indikator cyber.
6. Menjalankan jobs terotorisasi; dashboard menampilkan progress, kegagalan, dan sumber.
7. Analis mereview temuan teknis: URL, timestamp, IOC, relevansi, keterbatasan identitas.
8. Hanya temuan keamanan yang tervalidasi masuk ke dossier kasus; yang inconclusive dipisahkan.
9. Supervisor mereview insiden yang perlu eskalasi; laporan terbit sesuai RBAC.

### 4.2 USB Security

1. Pemilik HP menerima penjelasan ruang lingkup dan memberikan persetujuan spesifik, sukarela, terdokumentasi.
2. Examiner memulai sesi dengan Case ID, mencatat platform/perangkat minimum dan status otorisasi.
3. Desktop menguji konektivitas Android/iPhone melalui antarmuka resmi yang tersedia.
4. Pemeriksaan dibatasi pada security metadata dan indikator ancaman yang tersedia tanpa mengambil konten pribadi.
5. Jika OS/versi tidak mendukung pengambilan indikator, tampilkan `Unsupported/Not Available` - bukan `Clean`.
6. Examiner dapat menghentikan sesi; pencabutan persetujuan menghentikan pekerjaan terkait.
7. Manifest hash dan bukti teknis yang diizinkan disimpan lokal secara terenkripsi.
8. Sinkronisasi metadata/hasil yang disetujui dilakukan ketika online, dengan konflik ditinjau manusia.

## 5. Risiko dan asumsi

| Risiko | Penanganan awal |
|---|---|
| Nama umum menghasilkan false matches | Nama hanya referensi kasus; tidak ada auto-link ke akun personal. |
| Sistem digunakan untuk profiling sifat pribadi | Larangan eksplisit, akses dibatasi, audit, testing anti-misuse. |
| API eksternal berubah/limit | Adapter per sumber, simulasi, rate limit, retry terbatas. |
| iOS dan Android membatasi akses USB | Capability matrix per OS dan indikator `unsupported`. |
| HP pribadi memuat data sensitif | Data minimization, pilihan pemeriksaan, revocable consent. |
| Offline 8 jam membatasi revocation segera | Short-lived session, local lock, enforce revocation saat reconnect. |
| Solo developer dan kontrol enterprise kompleks | Bangun vertical slice, feature flags, test gates, review independen. |
| WORM/backup dan retensi konflik | Desain object lifecycle, legal hold, kebijakan penanggung jawab data. |
| Hash benar tetapi konteks bukti salah | Metadata provenance, signing, examiner verification, chain of custody. |

## 6. Roadmap hasil brainstorming

| Fase | Bulan | Target |
|---|---|---|
| Prototype | 1-2 | Simulation-first, wizard, portal, case, basic USB adapter mocks, queue, reports skeleton. |
| Security Validation | 3-4 | MFA/RBAC/mTLS, SQLCipher/KMS integration, audit+WORM, PITR, tests, fail-safe. |
| Controlled Pilot | 5 | Real cyber sources yang diotorisasi, 1 Android + 1 iPhone uji, independent review. |
| Operational Readiness | 6 | Hardening, runbooks, recovery drill, benchmark, Supervisor go/no-go. |

## 7. Urutan kelanjutan brainstorming

Pertanyaan yang belum dijawab: **pilihan SLA tanggapan insiden** (Fixed / Risk-Adaptive / Supervisor-Controlled). Setelah itu: definisi hak akses ekspor bukti, data retention schedule resmi, capability matrix Android/iOS, cloud vendor, budget, serta dokumen penilaian privasi dan dasar kewenangan. Buka kembali keputusan yang terlalu berat untuk MVP jika benchmark solo developer menunjukkan keterbatasan.

---

**Catatan:** Dokumen ini adalah konsolidasi pilihan diskusi, bukan bukti bahwa integrasi atau kemampuan teknis sudah tersedia. Semua interaksi eksternal dan pemeriksaan perangkat harus ditinjau ulang terhadap izin, batas API, keamanan, dan hukum yang berlaku sebelum pilot.
