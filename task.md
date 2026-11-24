# MARGONO - Engineering Tasks & Delivery Plan

**Version:** 1.0  
**Date:** 23 November 2026  
**Inputs:** `brainstorming.md`, `prd.md`  
**Execution model:** Solo developer + AI, 6 months, simulation-first  
**Status legend:** `[ ]` open, `[x]` done.

## 1. Delivery Rules

1. Build in small vertical slices: browser UI -> FastAPI endpoint -> PostgreSQL persistence -> simulated worker -> test -> evidence trail.
2. Never silently substitute synthetic results for real-world findings. Simulation output must be clearly labeled `SIMULASI` / `SYNTHETIC`.
3. Do not create features to infer sexual orientation, LGBT status, gender identity, relationship status, or personnel suitability. Do not enumerate personal social media accounts by name or extract personal phone content.
4. Gate all device work on explicit, revocable, purpose-specific consent and official operating-system capabilities.
5. Use no real personal data, external API keys, or connected devices in simulation tests.
6. Keep migrations reversible where feasible, feature flags for risky integrations, and explicit test evidence per task.
7. Tasks referencing advanced cloud controls may require provider selection; use secure interfaces/mocks first, do not claim a mocked security mechanism is deployed.
8. The 6-month target is a plan, not a guarantee. Defer low-priority presentation features before critical security controls.

## 2. Suggested Monorepo Layout (planning, no code yet)

```text
margono/
  brainstorming.md
  prd.md
  task.md
  codex_prompt.md
  apps/
    web/                 # React + Vite: Portal + Web Intelligence
    desktop/             # Tauri + React + Rust: USB Security workspace
  services/
    api/                 # FastAPI: auth, case, review, sync, reports
    worker/              # Procrastinate/PostgreSQL background jobs
  packages/
    ui/                  # Shared React components, dual themes
    contracts/           # API/event/data schemas shared where possible
  infra/
    local/               # Local container orchestration for dev only
    cloud/               # Reviewed private cloud manifests, staged
  fixtures/
    cases/               # 20 synthetic golden cases
    devices/             # 1 Android and 1 iPhone simulated profiles
    scenarios/           # deterministic seeded scenarios
  docs/
    architecture/
    security/
    operations/
  tests/
    e2e/
    security/
    recovery/
```

## 3. Epic and Dependency Map

| Epic | Workstream | Required before |
|---|---|---|
| E00 | Governance and scope boundaries | All real integrations |
| E01 | Dev environment and contracts | E02-E13 |
| E02 | Auth, RBAC and portal | Protected workflows |
| E03 | Case/import/duplicate UI | OSINT jobs |
| E04 | Source adapters and analyst review | Reports |
| E05 | Desktop mock and consent | Real USB connectors |
| E06 | Queue and sync | Offline E2E |
| E07 | Evidence and reports | Pilot approval |
| E08 | Encryption, PKI, keys | Real-data pilot |
| E09 | Audit, alerts, retention, DR | Real-data pilot |
| E10 | Automated testing and benchmarks | Every release gate |
| E11 | Controlled integrations | Pilot only |
| E12 | Release readiness | Production-like use |

## 4. Six-Month Sprint Plan

### Month 1 - Sprint 1: Governance, requirements, repository

- [x] **T-001 (P0, E00)** Freeze allowed use cases and explicit non-goals in docs and API contracts. **DoD:** policy assertions appear in PRD, sample consent, test plans, and review checklist. [FR-028] Policy and verification: `docs/acceptable-use.md`.
- [x] **T-002 (P0, E00)** Write preliminary data flow and threat model. **DoD:** trust boundaries for browser, desktop, workers, cloud, mobile and external APIs documented. [NFR-security] Preliminary model: `docs/simulation.md`.
- [x] **T-003 (P0, E01)** Initialize monorepo structure and root documentation. **DoD:** reproducible local environment and a readme that links source docs. Local setup and validation: `README.md`.
- [ ] **T-004 (P0, E01)** Establish tooling: dependency locks, formatting, type checking, unit tests, secrets scanning, CI. **DoD:** clean baseline CI passes. Local verification: `docs/development-checks.md`. GitHub Actions verification of the updated workflow is pending.
- [x] **T-005 (P0, E01)** Design data schema and migrations for users, roles, cases, consent, import rows, jobs and audit. **DoD:** migrations run on clean DB and test DB. [FR-010, FR-012] Migration and integration tests: `docs/database.md`.
- [x] **T-006 (P0, E01)** Define API contract conventions, error schema, UTC timestamps, correlation ID, idempotency key. **DoD:** example request/response fixtures documented. Contracts and examples: `docs/api-contract.md`.
- [x] **T-007 (P0, E10)** Generate 20 fixed synthetic case fixtures and seeded variation generator. **DoD:** identical seed reproduces identical scenarios. [FR-064] Catalog and seed tests: `services/api/tests/test_simulation.py`.
- [x] **T-008 (P0, E10)** Create explicit synthetic source and mobile profiles. **DoD:** zero real person records, clear synthetic labels. [FR-035] Synthetic profiles and tests: `services/api/tests/test_simulation.py`.

### Month 1 - Sprint 2: Authentication and operational portal

- [ ] **T-009 (P0, E02)** Implement internal account model, password hardening, test auth path. **DoD:** negative login cases covered; no default/shared production passwords. [FR-001]
- [ ] **T-010 (P0, E02)** Implement RBAC middleware and case-scoped policy checks. **DoD:** 4 roles enforced by API; unauthorized tests fail closed. [FR-002]
- [ ] **T-011 (P0, E02)** Build Workspace Selection Portal. **DoD:** Web and USB cards render by allowed role, system state displayed. [FR-003]
- [ ] **T-012 (P0, E02)** Build shared design tokens, dark/light themes, accessible components. **DoD:** both themes pass contrast checks on primary screens. [FR-004]
- [ ] **T-013 (P0, E02)** Implement role-aware notifications and sample activity queue cards. **DoD:** synthetic events shown without exposing case data to unauthorized roles. [FR-003]
- [ ] **T-014 (P0, E10)** Add authorization regression matrix per role. **DoD:** tests cover read/write/export/approve as allowed/denied.

### Month 2 - Sprint 3: Case + guided import + analyst review

- [ ] **T-015 (P0, E03)** Create Case CRUD with unique Case ID, purpose and status. **DoD:** create/open/close on synthetic cases, audit emitted. [FR-010]
- [ ] **T-016 (P0, E03)** Add XLSX/CSV upload with file size, encoding, type and malware-safe validation. **DoD:** malformed and oversized files rejected safely. [FR-020]
- [ ] **T-017 (P0, E03)** Build Guided Wizard, column mapping and row preview. **DoD:** user chooses `Nama` column and confirms import. [FR-021]
- [ ] **T-018 (P0, E03)** Implement duplicate row grouping without identity merge. **DoD:** same-name cases remain distinct unless human explicitly resolves. [FR-022]
- [ ] **T-019 (P0, E04)** Define adapter interface for public cyber indicators with simulated data. **DoD:** fixture adapter returns source/ref, timestamp, IOC and result state. [FR-023]
- [ ] **T-020 (P0, E04)** Build analyst review queue and evidence checklist. **DoD:** Verified/Inconclusive/Rejected supported; no automatic person inference. [FR-025, FR-026]
- [ ] **T-021 (P0, E10)** Add tests against same-name false matches, malicious file names/links and source poisoning. **DoD:** results never auto-linked to personal profile. [FR-028]

### Month 2 - Sprint 4: Desktop mock, queue, shared evidence, reports

- [ ] **T-022 (P0, E05)** Scaffold Tauri app with common UI theme and local SQLite persistence. **DoD:** signed-test build launches on Windows. [FR-030]
- [ ] **T-023 (P0, E05)** Implement explicit examination consent flow and withdrawal in mock mode. **DoD:** scope is visible and scanning blocked without consent. [FR-012]
- [ ] **T-024 (P0, E05)** Build Android/iPhone capability matrix and mock adapters. **DoD:** unsupported cases displayed as unavailable, not safe. [FR-031, FR-035]
- [ ] **T-025 (P0, E06)** Integrate PostgreSQL Procrastinate worker and local SQLite persistent queue. **DoD:** restart preserves queued jobs. [FR-040]
- [ ] **T-026 (P0, E06)** Implement pause/resume/cancel/retry, checkpoints, bounded backoff and idempotency. **DoD:** duplicate execution does not duplicate evidence. [FR-041, FR-042]
- [ ] **T-027 (P0, E06)** Build Advanced Monitoring UI. **DoD:** status API, job logs and progress on synthetic workload. [FR-043]
- [ ] **T-028 (P0, E07)** Build immutable evidence reference and SHA-256 manifest schema. **DoD:** file hash validated at ingest and download. [FR-011]
- [ ] **T-029 (P0, E07)** Add Executive and Technical report templates using synthetic cases. **DoD:** both reports share Case ID and differ by authorized content. [FR-060]
- [ ] **T-030 (P0, E10)** E2E smoke test of portal -> import -> mock findings -> mock USB -> case -> reports. **DoD:** 20 fixture cases complete. [G-01]

### Month 3 - Sprint 5: Security foundation

- [ ] **T-031 (P1, E02)** Enforce MFA enrollment and recovery for real accounts. **DoD:** MFA negative tests pass; recovery audited. [FR-001, FR-005]
- [ ] **T-032 (P1, E08)** Encrypt local SQLite with SQLCipher and protect local keys with Windows facility. **DoD:** stolen database file unreadable without key. [FR-050]
- [ ] **T-033 (P1, E08)** Add private-cloud KMS abstraction and no-secrets-in-source policy. **DoD:** test with provider-backed staging keys; permission-denied tests. [FR-051]
- [ ] **T-034 (P1, E08)** Establish mTLS gateway, internal device cert issuance and revocation. **DoD:** unregistered/cert-revoked laptop rejected. [FR-052]
- [ ] **T-035 (P1, E08)** Add one-time invitation and Administrator-approved enrollment. **DoD:** replayed/expired invitation rejected; private key not exported. [FR-053]
- [ ] **T-036 (P1, E08)** Implement 8-hour max offline authorization and automatic lock. **DoD:** simulated clock and reconnect cases validated. [FR-045]
- [ ] **T-037 (P1, E05)** Propagate consent revocation into local and cloud jobs. **DoD:** queued scan denied after withdrawal. [FR-013, FR-046]

### Month 3 - Sprint 6: Evidence-first synchronization

- [ ] **T-038 (P0, E06)** Implement sync protocol with versioned records and idempotent operations. **DoD:** repeat sync does not mutate original evidence. [FR-044]
- [ ] **T-039 (P1, E06)** Implement conflict detection and analyst review rather than silent overwrite. **DoD:** two-client conflict reproducible and resolved via audit event. [FR-044]
- [ ] **T-040 (P1, E07)** Define signed evidence manifest and trust anchor. **DoD:** tampered manifest or object fails verification. [FR-056]
- [ ] **T-041 (P1, E07)** Add quarantine and discrepancy report for recovery/transfer mismatches. **DoD:** problematic evidence is not marked verified. [FR-056]
- [ ] **T-042 (P1, E10)** Run offline/interrupted USB/network/bad clock scenarios. **DoD:** no silent loss, explicit failure states. [FR-065]
- [ ] **T-043 (P1, E08)** Design rotation and Supervisor-approved KMS recovery. **DoD:** controlled recovery dry-run + signed audit record. [FR-055]

### Month 4 - Sprint 7: Audit, retention, disaster recovery

- [ ] **T-044 (P1, E09)** Add hash-linked audit events and verified digital signatures. **DoD:** broken chain detected. [FR-058]
- [ ] **T-045 (P1, E09)** Push signed audit anchors/copies into WORM-capable private-cloud storage. **DoD:** write-once retention behavior documented and tested. [FR-058]
- [ ] **T-046 (P1, E09)** Implement periodic + event-driven audit integrity checks. **DoD:** tamper simulation triggers Supervisor alert. [FR-058]
- [ ] **T-047 (P1, E09)** Implement retention class and legal-hold models, dry-run deletion report. **DoD:** data due for deletion listed without violating holds. [FR-014]
- [ ] **T-048 (P1, E09)** Configure encrypted isolated backups and PostgreSQL PITR. **DoD:** recover test instance to selected timestamp. [FR-057]
- [ ] **T-049 (P1, E09)** Create cloud/device-loss runbook. **DoD:** simulated lost device results in cert/token revoke and evidence restore. [FR-054, FR-056]

### Month 4 - Sprint 8: Alerts, reports, validation

- [ ] **T-050 (P1, E09)** Implement multi-channel notification service with no sensitive evidence in email. **DoD:** dashboard, desktop, test official-email gateway and delivery audit. [FR-059]
- [ ] **T-051 (P1, E07)** Add Supervisor approval and controlled report export. **DoD:** unauthorized exports denied and logged. [FR-061]
- [ ] **T-052 (P1, E08)** Test certificate expiry max 90 days, conditional renewal and emergency rotation. **DoD:** expiry and revocation policies enforced. [FR-054, FR-055]
- [ ] **T-053 (P1, E10)** Run comprehensive security test suite and fix all critical issues. **DoD:** 100% of critical security checks pass. [Release Gate B]
- [ ] **T-054 (P1, E10)** Run 20 golden E2E cases, log performance baselines. **DoD:** all 20 flows pass, p50/p95 and error rates reported. [G-01]
- [ ] **T-055 (P1, E10)** Obtain independent security review and remediate priority findings. **DoD:** signed/recorded review summary. [Gate B]

### Month 5 - Sprint 9: Controlled connector integration

- [ ] **T-056 (P1, E11)** Approve permitted external source inventory and API ToS. **DoD:** each source has owner, purpose, rate limits, credentials and retention approval. [FR-024]
- [ ] **T-057 (P1, E11)** Integrate first real **organization/IOC-oriented** public cyber threat source. **DoD:** source attribution, audit, rate limit, error handling; no personal name profiling. [FR-024]
- [ ] **T-058 (P1, E11)** Build local offline signed threat feed update workflow. **DoD:** invalid signature rejected and previous valid version retained. [FR-034]
- [ ] **T-059 (P1, E11)** Validate actual supported Android diagnostics using consented test phone. **DoD:** capability matrix updated, only allowed metadata collected. [FR-032]
- [ ] **T-060 (P1, E11)** Validate actual supported iPhone diagnostics using consented test phone. **DoD:** platform limitations documented; unsupported checks honest. [FR-033]
- [ ] **T-061 (P1, E11)** Review privacy, authorization, volunteer consent, report outputs and pilot scope. **DoD:** Supervisor can issue written Go/No-Go. [Gate C]

### Month 5 - Sprint 10: Pilot execution

- [ ] **T-062 (P1, E11)** Run supervised pilot with limited approved cyber-source data. **DoD:** complete evidence and review trail for each test case. [Gate C]
- [ ] **T-063 (P1, E11)** Run Android/iPhone USB tests with revocable consent. **DoD:** collection never exceeds declared scope and can be stopped. [Gate C]
- [ ] **T-064 (P1, E10)** Test intermittent connectivity, USB disconnects, cloud downtime and local restore. **DoD:** work is recoverable or explicitly marked unavailable. [G-06]
- [ ] **T-065 (P1, E11)** Collect technical issues, operator feedback and unsupported capabilities. **DoD:** known limitations published, no false 'clean' claims.

### Month 6 - Sprint 11: Hardening and operations

- [ ] **T-066 (P1, E12)** Remediate all critical pilot findings and repeat regression tests. **DoD:** no open critical release blockers. [Gate D]
- [ ] **T-067 (P1, E12)** Finalize DR, certificate enrollment/revocation, key recovery, consent, export and audit runbooks. **DoD:** dry-run steps are executable by designated operator.
- [ ] **T-068 (P1, E12)** Execute recovery rehearsal including signed manifest validation. **DoD:** discrepancy and quarantine paths demonstrated. [FR-056, FR-057]
- [ ] **T-069 (P1, E12)** Finalize deployment documentation and logging/monitoring dashboard. **DoD:** installation and rollback on clean staging environment successful.
- [ ] **T-070 (P1, E12)** Review retention/deletion policy and tenant separation with data owner. **DoD:** policy sign-off, no indefinite retention by default.

### Month 6 - Sprint 12: Operational readiness and handover

- [ ] **T-071 (P1, E12)** Publish final benchmark report from simulated and controlled workloads. **DoD:** metrics traceable to run ID, platform and source versions.
- [ ] **T-072 (P1, E12)** Publish operator manual for four RBAC roles and known mobile limitations. **DoD:** each role can complete scenario without developer intervention.
- [ ] **T-073 (P1, E12)** Perform final penetration/security review and close release blockers. **DoD:** recorded review findings and mitigations. [Gate D]
- [ ] **T-074 (P1, E12)** Compile final Go/No-Go packet for Supervisor. **DoD:** tests, risk register, approvals and operating constraints in one package. [Gate D]
- [ ] **T-075 (P1, E12)** Tag release only after Supervisor decision. **DoD:** immutable build provenance and rollback plan recorded.

## 5. Cross-Cutting Test Matrix

| Test ID | Scenario | Expected result | Priority |
|---|---|---|---|
| TC-001 | Import 20 synthetic cases | Rows validated, source provenance retained | Critical |
| TC-002 | Two identical names | Distinct records; no auto identity linkage | Critical |
| TC-003 | CSV formula payload | Safely displayed/escaped; no execution | Critical |
| TC-004 | API source timeout | Retry bounded, failure visible, no duplicate | Critical |
| TC-005 | Offline queue restart | Jobs persist and resume idempotently | Critical |
| TC-006 | Owner declines/withdraws consent | USB collection disabled/cancelled | Critical |
| TC-007 | iPhone unsupported diagnostic | `Not available`, not `safe` | Critical |
| TC-008 | RBAC unauthorized evidence access | HTTP deny and audit event | Critical |
| TC-009 | Invalid MFA/session | No protected operation | Critical |
| TC-010 | Revoked device certificate online | mTLS session/access denied | Critical |
| TC-011 | Offline authorization beyond 8h | Access locked, new collection blocked | Critical |
| TC-012 | Manipulated evidence bytes | SHA-256 verification fails | Critical |
| TC-013 | Signed manifest alteration | Signature verification fails | Critical |
| TC-014 | Chain-of-custody gap | Explicit integrity alert / review required | Critical |
| TC-015 | WORM log tampering | Discrepancy detected, alert generated | Critical |
| TC-016 | Restore to PITR timestamp | Database restored and validated | Critical |
| TC-017 | Duplicate sync event | Single logical result maintained | Critical |
| TC-018 | Mismatched cloud vs local evidence | Reviewer conflict; no silent overwrite | Critical |
| TC-019 | Reports with different permissions | Executive/technical view obey RBAC | Critical |
| TC-020 | Any request for sensitive personal inference | No detection/scoring feature; rejected scope | Critical |
| TC-021 | Updated signed threat feed | Accepted; source version traceable | Noncritical until pilot |
| TC-022 | Corrupt/unsigned threat feed | Rejected and prior valid feed retained | Critical before pilot |
| TC-023 | SMTP gateway offline | Alert queued, dashboard still available | Noncritical |
| TC-024 | Desktop light/dark themes | Accessible and consistent | Noncritical |
| TC-025 | Performance under repeatable seed | Benchmark reproducible | Noncritical |

## 6. Release Gates and Evidence Checklist

### Gate A - Prototype

- [ ] Twenty fixed synthetic cases run end-to-end.
- [ ] Both workspace mock journeys demonstrable.
- [ ] Reports and Case ID integration complete.
- [ ] No real personal data or personal phone content used.

### Gate B - Security Validation

- [ ] All critical tests pass; no known critical vulnerability.
- [ ] Backup/PITR and evidence checks demonstrated.
- [ ] mTLS enrollment/revocation and 8h offline authorization demonstrated.
- [ ] Independent security review completed.

### Gate C - Controlled Pilot

- [ ] Sources and phone diagnostics approved and realistically supported.
- [ ] Voluntary consent and stop mechanism verified.
- [ ] Supervisor written authorization and legal/privacy clearance recorded.
- [ ] Pilot evidence, alert and incident workflows ready.

### Gate D - Operational Readiness

- [ ] Security regressions and benchmark published.
- [ ] Documentation/runbooks complete.
- [ ] Retention/legal hold implemented and approved.
- [ ] Supervisor Go/No-Go issued.

## 7. Engineering Decisions to Confirm Before Implementation

- [ ] **OPEN-01:** Incident response SLA (Fixed / Risk-Adaptive / Manual); currently **undecided**.
- [ ] **OPEN-02:** Private-cloud vendor, region, storage, KMS and WORM implementation.
- [ ] **OPEN-03:** MFA factor choice and secure recovery process.
- [ ] **OPEN-04:** Real Android/iPhone capability support and minimum OS versions.
- [ ] **OPEN-05:** Approved external cyber threat APIs and their policies.
- [ ] **OPEN-06:** Official data classification, consent/legal-hold and retention schedule.
- [ ] **OPEN-07:** Alert gateway and official email provider.
- [ ] **OPEN-08:** Definition of incident severity and acknowledgment semantics.

## 8. Next Immediate Tasks for Codex

1. Read all Markdown specs and produce a consistency/open-decision report before making implementation choices.
2. Start with **T-001 through T-008** and do not skip guardrails or test-fixture generation.
3. Create only simulation-mode scaffolding during initial delivery; external adapters must be disabled by default.
4. Demonstrate a vertical slice for one synthetic case before implementing all 20.
5. For each completed task, update this checklist with a concise commit/test reference.

---

**Definition of Done:** A task is not complete just because UI appears functional. It requires automated test coverage, documented limitations, failure-mode behavior, and enforcement of cybersecurity-only purpose and privacy constraints.
