# MARGONO - Product Requirements Document (PRD)

**Version:** 1.0  
**Date:** 23 November 2026  
**Source:** `brainstorming.md`  
**Status:** Draft for planning and technical review  
**Owner:** Solo developer, assisted by AI  
**Target:** Simulation-first MVP and controlled pilot across 6 months

## 1. Executive Summary

MARGONO is a secure cybersecurity case-management platform with two integrated workspaces:

1. **Web Intelligence:** authorized examination of objective public cybersecurity signals, structured import for case reference, source validation, analyst verification, and batch progress tracking.
2. **USB Security Diagnostics:** consent-based examination of limited security metadata and permitted technical threat indicators on personally owned Android and iPhone devices from a Windows desktop application.

Both share internal MFA, four-role RBAC, Case ID, evidence provenance, dual reporting, an encrypted offline-to-private-cloud sync model, and tamper-evident audit trails.

**Safety boundary:** The platform must not identify, infer, label, score, or predict sexual orientation, gender identity, intimate relationships, other sensitive personal characteristics, or personnel suitability based on those characteristics. It must not mass-enumerate personal social media accounts from name lists, and it must not extract private phone communications or personal media. Case handling remains human reviewed and focused on independently verifiable cybersecurity events.

See [acceptable use and review criteria](docs/acceptable-use.md) for the simulation boundary and consent example.

## 2. Problem Statement

Cybersecurity analysts may manage fragmented datasets: security-relevant public indicators, mobile diagnostic metadata from consent-based sessions, authorization records, and investigation files. Inconsistency between tools can lead to lost provenance, duplicate jobs, unreviewed false positives, and incomplete audit history. MARGONO aims to create a traceable, secure workflow without over-collecting personal data.

## 3. Product Goals and Non-Goals

### 3.1 Goals

- **G-01:** Prove a full end-to-end workflow across both workspaces for **20 synthetic cases and 2 test devices**.
- **G-02:** Preserve verifiable evidence integrity (SHA-256, signed manifest, provenance, chain of custody).
- **G-03:** Protect personal information through minimized data collection, revocable consent, MFA, RBAC, encryption, and retention rules.
- **G-04:** Provide a usable analyst workflow: import, review, scan, sync, alerts, supervisor review, and two report types.
- **G-05:** Allow a local desktop session to continue offline for at most 8 hours under a current authorization grant, with audited sync on reconnection.
- **G-06:** Demonstrate controlled recovery from failed jobs, interrupted networks, device loss, and backup restore.

### 3.2 Explicit non-goals

- Inference of LGBT status, sexual orientation, gender identity, intimate relationships, or private lifestyle.
- Background surveillance or OSINT-based personal profiling by name.
- Broad personal-account discovery, scraping behind authentication, bypass of access controls, or circumvention of social media platform terms.
- Covert phone examination, full phone extraction, jailbreak/root exploitation, unauthorized access, reading messages/photos/contacts/browser history, or scanning without valid consent.
- Automated adverse personnel decisions, person-centric risk scores, or automatic identity confirmation from a name.
- A claim of universal malware detection across Android and iOS.

## 4. Users, Roles, and Authorization

| Role | Permitted core actions | Restrictions |
|---|---|---|
| Administrator | Provision users, MFA, role assignment, device enrollment, certificate revocation, system configuration | No default access to private evidence content. |
| OSINT Analyst | Import/reference cases, run approved source checks, review cyber indicators, annotate provenance | No USB examination or case-final approval unless separately granted. |
| Forensic Examiner | Capture device consent, perform supported security diagnostics, review and sync technical findings | No personal content acquisition or access beyond consent scope. |
| Supervisor | Approve pilot, validate serious incidents, authorize report release, approve key recovery/migration exceptions | Cannot rewrite raw immutable evidence or bypass audit. |

- Every operation is authorized server-side. Frontend navigation visibility is not an authorization control.
- Internal accounts require MFA and secure account recovery.
- Administrative actions, report export, key recovery, device enrollment, and consent withdrawal must emit audit events.
- Separation of duties is preferable for critical evidence operations; evaluate necessity against the four-role RBAC decision.

## 5. Primary User Journeys

### 5.1 UJ-01: Login and portal

1. Operator signs in with a dedicated account plus MFA.
2. Portal displays status of private cloud, queued tasks, notifications, and connectivity.
3. User selects Web Intelligence or USB Security workspace.
4. Available menu items match role grants; unauthorized API calls are rejected.

### 5.2 UJ-02: Import and public cyber signal review

1. Analyst selects an authorized Case ID and records the specific cybersecurity purpose.
2. Guided Wizard accepts `.xlsx` or `.csv`, previews data, maps the `Nama` column, and validates format.
3. Duplicate names are flagged for human review; name remains only a case label.
4. Analyst selects permitted cyber threat sources and organization-specific IOCs/known URLs/domains for querying.
5. The job enters the persistent queue; user monitors progress and errors.
6. Each result is tagged with source, URL/ref, retrieval timestamp, scope, and verification state.
7. Analyst verifies objective cyber relevance. Results with ambiguous personal identity remain Inconclusive and cannot be used for personnel conclusions.
8. Approved technical findings are linked to Case ID with evidence manifest and audit history.

### 5.3 UJ-03: Consent-based USB security examination

1. Examiner creates a scoped examination session under Case ID.
2. Phone owner reads and voluntarily accepts specific diagnostics and retention; consent can be withdrawn.
3. Desktop connects via USB and identifies supported platform capabilities (Android/iPhone) using permitted interfaces.
4. The tool checks only supported non-content security metadata / technical threat indicators.
5. Unsupported indicators are `Not available`; the device is never labeled `Safe` merely due to a negative check.
6. Operator can pause/cancel; consent revocation stops related jobs and new collection.
7. Findings are stored locally encrypted, hashed, signed where appropriate, then synced in minimized form when authorized.

### 5.4 UJ-04: Case review and dual report

1. Analyst/Examiner associates verified findings to Case ID.
2. Supervisor views evidence provenance, limitations, severity and review states.
3. Two separate views are generated: concise Executive Report, detailed Technical Forensic Report.
4. Release/export is authorized and audited; recipient only sees entitled data.

### 5.5 UJ-05: Device migration and recovery

1. Administrator revokes compromised/lost device certificate when possible.
2. New laptop performs Controlled Enrollment with one-time invitation and a fresh private key.
3. Data synced to cloud is restored; available offline data is migrated only via approved encrypted path.
4. Hashes and signed manifests are verified, discrepancies quarantined, Supervisor signs off on exception recovery.

## 6. Functional Requirements

Requirement priority: **P0 = necessary for simulated end-to-end MVP**, **P1 = required prior to limited real-data pilot**, **P2 = later improvement**. Chosen architecture is maintained even if full rollout of some controls is staged.

### 6.1 Identity, RBAC, portal

| ID | Priority | Requirement / acceptance condition |
|---|---|---|
| FR-001 | P0 | Internal account login, non-production demo login only in sandbox; MFA enforced for real users before pilot. |
| FR-002 | P0 | Four server-enforced roles; negative authorization tests for every restricted action. |
| FR-003 | P0 | Operational Portal with workspace selector, queue health, sync state, and role-filtered notifications. |
| FR-004 | P0 | Dark/light theme consistent on web and desktop. |
| FR-005 | P1 | Secure account recovery, authentication event audit, session expiry and revocation. |

### 6.2 Case and consent management

| ID | Priority | Requirement / acceptance condition |
|---|---|---|
| FR-010 | P0 | Unique Case ID with status, owner/role access, purpose, creation/closure timestamps. |
| FR-011 | P0 | Attachment and finding metadata has provenance, immutable source ID, version and hash. |
| FR-012 | P0 | Consent record includes scope, purpose, device session, time, plain-language disclosure, operator, status. |
| FR-013 | P1 | Consent withdrawal reliably cancels pending device tasks and prevents further collection. |
| FR-014 | P1 | Policy-based retention with legal hold, staged deletion, evidence archive controls. |
| FR-015 | P1 | Explicit data export permissions and approvals, audited. |

### 6.3 Web Intelligence workspace

| ID | Priority | Requirement / acceptance condition |
|---|---|---|
| FR-020 | P0 | Guided Wizard accepts XLSX/CSV and manually entered labels; handles encoding and malformed rows. |
| FR-021 | P0 | Smart Column Mapping for `Nama`; preview, row validation, empty/duplicate reporting. |
| FR-022 | P0 | Smart Duplicate Review: group possible duplicate rows, no automatic merge of person identity. |
| FR-023 | P0 | Public cybersecurity source adapters have a deterministic mock implementation and stable result schema. |
| FR-024 | P1 | Real adapters only for authorized, publicly available cyber sources / permitted APIs; provider rate limits and ToS respected. |
| FR-025 | P0 | Evidence-Based Verification checklist including original source, timestamp, IOC, relevance, confidence limitations and analyst decision. |
| FR-026 | P0 | Review status Verified / Inconclusive / Rejected, separate from security threat status. |
| FR-027 | P1 | Inconclusive findings isolated for scheduled review or policy-based deletion; cannot drive adverse personnel decisions. |
| FR-028 | P0 | No automatic identity matching of arbitrary personal accounts to uploaded names; no scoring or sensitive attribute inference. |

### 6.4 USB Security workspace

| ID | Priority | Requirement / acceptance condition |
|---|---|---|
| FR-030 | P0 | Desktop Tauri shell with Android/iPhone capability registry, real device permission checks and mock-mode demo. |
| FR-031 | P0 | Permissioned, non-content security metadata result model; a capability not supported reports `Unsupported` or `Not available`. |
| FR-032 | P1 | Android diagnostic adapter using permitted official interfaces after explicit user action; no bypass/exploit. |
| FR-033 | P1 | iPhone diagnostic adapter restricted to interfaces/data actually available after user trust/pairing/authorization. |
| FR-034 | P1 | Check permitted indicators against offline signed threat-intelligence snapshot, with provenance/version. |
| FR-035 | P0 | Reproducible mock scan for two synthetic phones with both success and unsupported branches. |
| FR-036 | P1 | Local evidence/data encrypted; no messages, photos, contacts, or private app content acquisition. |
| FR-037 | P0 | UI explains that absence of detected evidence is not proof of absence of compromise. |

### 6.5 Queue, sync, and monitoring

| ID | Priority | Requirement / acceptance condition |
|---|---|---|
| FR-040 | P0 | Procrastinate/PostgreSQL queue for server-side jobs; SQLite persistent queue for desktop. |
| FR-041 | P0 | Job states queued/running/paused/completed/failed/cancelled and idempotency keys. |
| FR-042 | P0 | Checkpoints and bounded retries with exponential backoff, timeout and provider rate handling. |
| FR-043 | P0 | Advanced Monitoring shows job progress, logs, API status, Pause/Resume/Cancel/Retry when supported. |
| FR-044 | P0 | Evidence-First Sync: immutable evidence references; merge safe metadata only; material conflicts to reviewer. |
| FR-045 | P1 | Offline grant max 8h, enforce lock and grant expiry; revocation enforced upon reconnection. |
| FR-046 | P1 | Consent withdrawal propagates to local/server queues and blocks pending device collection. |

### 6.6 Security, keys, enrollment, and recovery

| ID | Priority | Requirement / acceptance condition |
|---|---|---|
| FR-050 | P1 | SQLCipher at rest locally; Windows credential/key storage; TLS 1.3 wherever supported by managed components. |
| FR-051 | P1 | Private Cloud KMS for key lifecycle, key versions, authorized recovery and immutable audit. |
| FR-052 | P1 | mTLS and unique laptop certificates; no uncertified desktop can access protected APIs. |
| FR-053 | P1 | One-time invite enrollment and Administrator approval; private key generated/stored on device. |
| FR-054 | P1 | Certificate maximum lifetime 90 days; conditional renewal and online revocation. |
| FR-055 | P1 | Key rotation scheduled and event-driven, with tested old-data readability/re-encryption path. |
| FR-056 | P1 | Signed evidence manifest, verification on restore, discrepancy quarantine and Supervisor review. |
| FR-057 | P1 | PostgreSQL PITR and isolated encrypted backups with demonstrated restoration. |
| FR-058 | P1 | Hash-linked and digitally signed audit, WORM copy, event and periodic integrity checking. |
| FR-059 | P1 | Security alert fan-out to dashboard, desktop, approved official email, and authorized escalation. |

### 6.7 Reports, incident workflow, simulations

| ID | Priority | Requirement / acceptance condition |
|---|---|---|
| FR-060 | P0 | Executive and Technical report templates derived from one Case ID; all demo content labeled synthetic. |
| FR-061 | P1 | Approval/release and watermark/classification consistent with institution policy and RBAC. |
| FR-062 | P0 | Threat status Confirmed/Suspected/Inconclusive/False Positive for objective technical evidence only. |
| FR-063 | P0 | Separate severity Low/Medium/High/Critical and human review; no automatic personnel ranking. |
| FR-064 | P0 | Hybrid simulator: 20 fixed synthetic cases and seed-based reproducible dynamic scenarios. |
| FR-065 | P0 | Simulated network/API failures, USB disconnects, duplicate jobs, identity collisions, wrong signatures, auth denials. |
| FR-066 | P1 | Critical notifications reviewed by Supervisor with acknowledgment and incident timeline. |

## 7. Data Model (conceptual, not SQL)

| Entity | Key fields / purpose |
|---|---|
| `users`, `roles`, `user_role` | Operator identity, permissions, MFA state. |
| `trusted_devices` | Device ID, cert thumbprint, enrollment state, expiry, revoked_at. |
| `cases` | Case ID, scope, purpose, status, owner, retention profile. |
| `case_subject_labels` | Submitted names/labels, source row, ambiguity state, no identity claims. |
| `imports`, `import_rows` | Source file manifest, column mapping, validation diagnostics. |
| `jobs`, `job_events` | Persistent job state, checkpoint, idempotency, errors, retry history. |
| `device_sessions`, `consent_records` | Session authority, selected checks, disclosure, revocation. |
| `source_observations` | Cyber source identity, URL/ref, retrieved_at, raw metadata restricted. |
| `findings`, `reviews` | Objective technical evidence, source correlation, analyst decision. |
| `evidence_objects`, `evidence_manifests` | Immutable object refs, hashes, signing metadata, chain of custody. |
| `sync_events`, `conflicts` | Device/cloud versions, conflict decisions, reconciliation audit. |
| `threat_feeds`, `ioc_matches` | Signed feed version, IOC checks, provenance and validity. |
| `reports`, `approvals` | Report version, kind, release authorization, recipient scope. |
| `audit_events`, `audit_anchors` | Timestamped hash-chained events and WORM anchor references. |
| `retention_rules`, `legal_holds` | Retention schedule and policy exceptions. |
| `notifications`, `acknowledgments` | Channel, delivery/ack status, escalation chain. |

**Design invariant:** mutable operational state and immutable evidence objects are distinct. Deleting operational records must not silently delete evidence under legal hold; conversely, WORM storage is not an excuse for limitless retention.

## 8. API and Integration Boundaries (planning)

- API domains: `auth`, `portal`, `cases`, `imports`, `sources`, `reviews`, `device-sessions`, `consents`, `jobs`, `sync`, `evidence`, `reports`, `notifications`, `admin`, `audit`.
- All API inputs use schema validation; authorization is enforced on the server per case and action.
- Long-running jobs are asynchronous and idempotent. Status updates may use polling first; choose streaming only after benchmark.
- Source adapters must explicitly declare scope, authentication needs, rate limits, and data retention.
- Device adapters must declare platform, OS version, supported indicators, reason for unsupported values, and consent requirements.
- Never submit raw private phone content or personal profile data to public threat-intelligence services.

## 9. Security and Privacy Requirements

### 9.1 Data protection

- Encrypt sensitive data at rest and in transit; secrets belong in Windows Secure Storage or a cloud secret manager/KMS, never frontend bundles.
- Isolate real pilot data from synthetic development data; segregate keys, cloud projects, logs, and credentials.
- Use strict content security policy, CSRF defense as applicable, safe import parsing, MIME and size limits, and malware-safe file handling.
- RBAC must constrain data queries, reports, API jobs, evidence downloads, and notifications.
- Audit access to source links, local diagnostics, consent records, key recovery, export, revocation, migration, and deletion.

### 9.2 Consent and lawful use

- Consent must state examination purpose, exact indicator categories, retention, recipient roles, ability to decline, and ability to stop.
- Revocation stops new collection; existing records are retained or deleted per explicit lawful retention and legal hold policy, not silently overridden.
- No coercion, covert collection, or attempts to evade mobile OS security protections.
- No employment/security clearance decision inferred from the software output alone.

### 9.3 Threat modeling

At minimum review: malicious CSV/XLSX inputs, attacker-controlled URLs, API injection, lost laptop, stolen token, compromised device certificate, tampered update package, forged evidence manifest, malicious operator, unauthorized data export, sync replay, offline-clock tampering, queue overload, cloud outage, and compromised WORM credentials.

## 10. Nonfunctional Requirements

| Category | Requirement |
|---|---|
| Testability | Deterministic simulator with pinned fixtures and repeatable seeds. |
| Performance | Benchmark First; record per-step latency, p50/p95, throughput, retry counts. No invented target duration. |
| Integrity | 100% of sampled transferred evidence validates against signed manifest and trusted hash. |
| Authorization | 100% critical RBAC/MFA/consent negative tests pass before pilot. |
| Reliability | No silent data loss on simulated network interrupts; failed operations are visible and retryable when authorized. |
| Compatibility | Windows Tauri client; explicit Android/iPhone capability matrix; unsupported checks visibly labeled. |
| Recoverability | PITR restored in a documented drill; recovery of signed/hashed evidence verified. |
| Security | mTLS for desktop cloud access; KMS key rotation/recovery; 8-hour max offline grant. |
| Privacy | Minimum necessary records; segregated retention and deletion; no sensitive attribute inference. |
| Operability | Accessible dark/light UI, clear error states, Supervisor audit/review workflows. |

## 11. MVP Acceptance Criteria and Release Gates

### Gate A - Prototype (months 1-2)

- 20 fixed synthetic cases importable and traceable through review and dual report generation.
- 2 device mock workflows completed including success, failure, and unsupported capability paths.
- Queues demonstrate restart persistence, bounded retry, and idempotency.
- User interfaces include both workspace navigation and basic monitoring.
- No real personal source crawling or personal content extraction is enabled.

### Gate B - Security Validation (months 3-4)

- All critical tests for authorization, consent, integrity, audit, encrypted storage, sync, and recovery pass.
- 20 core end-to-end fixtures complete successfully.
- Risk/benchmark-informed thresholds documented for noncritical tests.
- Secure device enrollment, certificate validation, key recovery and revocation tested.
- Independent reviewer evaluates tests and threat model.

### Gate C - Controlled Pilot (month 5)

- Supervisor approves in writing after reviewing security assessment and lawful basis.
- 1 Android and 1 iPhone test device used only with scoped voluntary consent.
- Real connectors enabled only for approved public cybersecurity sources with allowed credentials.
- Unsupported platform checks are explicitly disclosed, no false assurance of full forensic extraction.
- Response handling, deletion, export, and incident reporting are audit-ready.

### Gate D - Operational Readiness (month 6)

- Documented recovery drill, monitoring, support, backup, key rotation, and release procedures.
- Open critical issues = 0; residual noncritical risks documented and approved.
- Approved reports, retention rules, and training/runbooks are available.
- Supervisor records final Go/No-Go decision; external independent audit strongly recommended.

## 12. Rollout Plan and Six-Month Timeline

| Month | Focus | Primary output |
|---|---|---|
| 1 | Architecture, repo, safe schemas, portal, synthetic case importer | Navigable skeleton, reproducible fixtures |
| 2 | Both workspaces, mock USB, queue, evidence, dual reports | Simulated end-to-end demonstration |
| 3 | MFA/RBAC, consent revocation, encrypted local data, mTLS enrollment | Security foundation |
| 4 | Signed audit/WORM, key lifecycle, DR/PITR, test automation | Comprehensive validation report |
| 5 | Controlled real-source / test-device adapters; limited pilot | Approved pilot records |
| 6 | Fix findings, benchmark, hardening, SOPs, readiness | Go/No-Go package |

## 13. Dependencies and Constraints

- **People:** solo developer; independent cybersecurity review and legal/privacy authorization before pilot.
- **Infrastructure:** private cloud with PostgreSQL, an approved KMS, compatible WORM retention mechanism, certificate/PKI service and backup target.
- **External systems:** only legitimate API/public source access; credentials and rate limits available when needed.
- **Mobile capabilities:** exact capability matrix for supported Android/iOS versions must be experimentally confirmed; unsupported remains a first-class state.
- **Legal/organizational:** data classification, retention, consent template and acceptable use reviewed by institutional authority.

## 14. Open Questions and Assumptions

1. Incident Response SLA selection remains **open** (Fixed, Risk-Adaptive, Supervisor-Controlled).
2. Hosting vendor, KMS, WORM provider, email gateway and private network specifics remain unspecified.
3. Mobile OS version support, Android/iPhone connector capabilities and device test hardware remain to be assessed.
4. Retention periods, storage class, legal hold authority, and incident severity taxonomy need policy owner signoff.
5. Invitation expiry, certificate issuer details, key backup policy and actual cryptographic profile require detailed security design.
6. Number of users, expected real-case throughput, allowed public threat sources, and external data-sharing terms are not yet agreed.

## 15. Definition of Done

A requirement is done only when the implementation is documented; testable; exercised by passing automated tests; reviewed against privacy and security boundaries; produces auditable, unambiguous states; and is demonstrable in a deterministic fixture. Production access additionally requires independent security review and Supervisor authorization.

---

**Source of truth:** `brainstorming.md` for decisions, this PRD for behavioral requirements, `task.md` for delivery sequencing. New choices must be reflected consistently in all three.
