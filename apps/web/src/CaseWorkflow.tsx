import { useEffect, useRef, useState, type FormEvent } from 'react';
import { isUuid } from './api';
import { isTimestamp } from './contracts';
import { formatTimestamp, selectionUrl } from './display';
import { isObject, operatorResponse, request, RequestError, type Session } from './operatorApi';

type OperatorProps = {
  session: Session;
  onSessionExpired: (id: string | null) => void;
};
const jobStatuses = {
  queued: 'Dalam antrean', running: 'Berjalan', paused: 'Dijeda',
  completed: 'Selesai', failed: 'Gagal', cancelled: 'Dibatalkan',
};
const reviewStatuses = {
  pending: 'Menunggu review', verified: 'Terverifikasi',
  inconclusive: 'Tidak meyakinkan', rejected: 'Ditolak',
};
type JobStatus = keyof typeof jobStatuses;
type ReviewStatus = keyof typeof reviewStatuses;
type Job = {
  id: string; case_id: string; kind: 'synthetic_source' | 'synthetic_device'; status: JobStatus; attempts: number;
  created_at: string; failure_code: string | null; scheduled_at: string | null; review_pending: boolean;
  consent_active: boolean;
};
type Finding = {
  id: string; severity: string; threat_status: string; verification: ReviewStatus;
  evidence_sha256: string; review_note: string | null;
  reviewed_by: string | null; reviewed_at: string | null;
  evidence: { source_ref: string; observed_at: string; indicator: string; limitation: string; import_id: string; import_sha256: string };
};

type ActivityPage<T> = { items: T[]; total: number; next: string | null };
type ReviewFilter = 'all' | ReviewStatus;

function decodeList<T>(value: unknown, valid: (item: unknown) => item is T): T[] {
  if (!Array.isArray(value) || !value.every(valid)) throw new Error('Unexpected list');
  return value;
}

function readCount(response: Response, name: string) {
  const value = response.headers.get(name);
  const count = Number(value);
  if (value === null || !/^\d+$/.test(value) || !Number.isSafeInteger(count)) throw new Error('Unexpected count');
  return count;
}

async function loadActivity<T>(path: string, session: Session, signal: AbortSignal, valid: (value: unknown) => value is T): Promise<ActivityPage<T>> {
  const response = await operatorResponse(path, { signal }, session);
  const items = decodeList(await response.json(), valid);
  const total = readCount(response, 'X-Total-Count');
  const next = response.headers.get('X-Next-Cursor');
  if (total < items.length || (next !== null && !isUuid(next))) throw new Error('Unexpected activity page');
  return { items, total, next };
}

function appendActivity<T extends { id: string }>(previous: ActivityPage<T>, next: ActivityPage<T>) {
  const known = new Set(previous.items.map((item) => item.id));
  return { ...next, items: [...previous.items, ...next.items.filter((item) => !known.has(item.id))] };
}

function isJob(value: unknown): value is Job {
  return isObject(value) && isUuid(value.id) && isUuid(value.case_id)
    && (value.kind === 'synthetic_source' || value.kind === 'synthetic_device')
    && typeof value.status === 'string' && Object.hasOwn(jobStatuses, value.status)
    && typeof value.attempts === 'number' && typeof value.review_pending === 'boolean'
    && typeof value.consent_active === 'boolean' && isTimestamp(value.created_at)
    && (value.failure_code === null || typeof value.failure_code === 'string')
    && (value.scheduled_at === null || isTimestamp(value.scheduled_at));
}

function isFinding(value: unknown): value is Finding {
  return isObject(value) && isUuid(value.id) && typeof value.severity === 'string'
    && typeof value.threat_status === 'string' && typeof value.verification === 'string'
    && Object.hasOwn(reviewStatuses, value.verification) && typeof value.evidence_sha256 === 'string'
    && (value.review_note === null || typeof value.review_note === 'string')
    && (value.reviewed_by === null || isUuid(value.reviewed_by))
    && (value.reviewed_at === null || isTimestamp(value.reviewed_at)) && isObject(value.evidence)
    && typeof value.evidence.source_ref === 'string' && isTimestamp(value.evidence.observed_at)
    && typeof value.evidence.indicator === 'string' && typeof value.evidence.limitation === 'string'
    && isUuid(value.evidence.import_id) && typeof value.evidence.import_sha256 === 'string';
}

export function useOperatorTask({ session, onSessionExpired }: OperatorProps) {
  const lifetime = useRef<AbortController>(null);
  const [busy, setBusy] = useState(false);
  const [issue, setIssue] = useState<{ message: string; id?: string | null }>();

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, [session]);

  async function run(action: (signal: AbortSignal) => Promise<void>, message: string) {
    const signal = lifetime.current?.signal;
    if (!signal || signal.aborted) return;
    setIssue(undefined);
    setBusy(true);
    try {
      await action(signal);
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof RequestError && error.status === 401) onSessionExpired(error.correlationId);
      else setIssue({
        message: error instanceof RequestError && error.status === 409
          ? 'Perubahan bertentangan dengan status terbaru. Muat ulang sebelum mencoba lagi.' : message,
        id: error instanceof RequestError ? error.correlationId : null,
      });
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  return { run, busy, issue };
}

function JobLine({ job }: { job: Job }) {
  return <>{job.kind === 'synthetic_source' ? 'Sumber' : 'Perangkat'} · {jobStatuses[job.status]} · {job.attempts} percobaan selesai
    {' · '}<time dateTime={job.created_at}>{formatTimestamp(job.created_at)}</time>
    {' · '}<code>{job.id}</code>
    {job.failure_code && <> · <code>{job.failure_code}</code></>}
    {job.status === 'queued' && job.scheduled_at && <> · Dijadwalkan <time dateTime={job.scheduled_at}>{formatTimestamp(job.scheduled_at)}</time></>}
  </>;
}

export function PortalJobs(props: OperatorProps & { onOpenCase: (caseId: string) => void }) {
  const { session, onOpenCase } = props;
  const { run, busy, issue } = useOperatorTask(props);
  const [jobs, setJobs] = useState<{ items: Job[]; total: number; failed: number; pending: number | null }>();
  const canReview = session.roles.some((role) => ['osint_analyst', 'supervisor'].includes(role));
  if (!session.roles.some((role) => ['supervisor', 'osint_analyst', 'forensic_examiner'].includes(role))) return null;
  return (
    <section aria-label="Pekerjaan portal">
      <h3>Pekerjaan portal</h3>
      <button type="button" disabled={busy} onClick={() => void run(async (signal) => {
        const response = await operatorResponse('/jobs', { signal }, session);
        const items = decodeList(await response.json(), isJob);
        const total = readCount(response, 'X-Total-Count');
        const failed = readCount(response, 'X-Failed-Count');
        const pending = canReview ? readCount(response, 'X-Pending-Review-Count') : null;
        signal.throwIfAborted();
        setJobs({ items, total, failed, pending });
      }, 'Pekerjaan portal gagal dimuat.')}>Muat pekerjaan portal</button>
      {issue && <p role="alert">{issue.message} {issue.id && <code>{issue.id}</code>}</p>}
      {jobs && <>
        <p role="status">{jobs.failed} pekerjaan gagal
          {jobs.pending !== null && <> · {jobs.pending} temuan menunggu review</>}
          {jobs.items.length < jobs.total && <> · Menampilkan {jobs.items.length} dari {jobs.total} pekerjaan</>}
          {' · '}Sinkronisasi desktop belum tersedia
        </p>
        {jobs.total === 0 && <p>Belum ada pekerjaan yang dapat Anda akses.</p>}
        <ul>{jobs.items.map((job) => <li key={job.id}>
          <a href={selectionUrl('saved', job.case_id).href} onClick={(event) => {
            if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            onOpenCase(job.case_id);
          }}>Buka kasus</a>{' · '}<JobLine job={job} />
        </li>)}</ul>
      </>}
    </section>
  );
}

export function CaseWorkflow({ caseId, open, deviceCase, ...props }: OperatorProps & { caseId: string; open: boolean; deviceCase: boolean }) {
  const { session } = props;
  const { run, busy, issue } = useOperatorTask(props);
  const [data, setData] = useState<{ jobs: ActivityPage<Job>; findings: ActivityPage<Finding> | null; collaborators: string[] }>();
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('pending');
  const [report, setReport] = useState<{ label: string; data: unknown }>();
  const path = `/cases/${caseId}`;
  const supervisor = session.roles.includes('supervisor');
  const analyst = session.roles.includes('osint_analyst');
  const canReview = open && (supervisor || analyst);
  const canReadTechnical = supervisor || analyst || (deviceCase && session.roles.includes('forensic_examiner'));
  const examiner = session.roles.includes('forensic_examiner');
  const pageSize = 25;
  const findingsPage = data?.findings;

  function loadFindings(filter: ReviewFilter, signal: AbortSignal, after?: string) {
    const query = new URLSearchParams({ limit: String(pageSize) });
    if (filter !== 'all') query.set('verification', filter);
    if (after) query.set('after', after);
    return loadActivity(`${path}/findings?${query}`, session, signal, isFinding);
  }

  function loadJobs(signal: AbortSignal, before?: string) {
    const query = new URLSearchParams({ limit: String(pageSize) });
    if (before) query.set('before', before);
    return loadActivity(`${path}/jobs?${query}`, session, signal, isJob);
  }

  async function refresh(signal: AbortSignal) {
    const [jobs, findings, collaborators] = await Promise.all(
      [loadJobs(signal), canReadTechnical ? loadFindings(reviewFilter, signal) : null,
        request(`${path}/collaborators`, { signal }, session)],
    );
    signal.throwIfAborted();
    setData({
      jobs, findings,
      collaborators: decodeList(collaborators, (item): item is string => typeof item === 'string'),
    });
  }

  function filterFindings(filter: ReviewFilter) {
    void run(async (signal) => {
      const findings = await loadFindings(filter, signal);
      signal.throwIfAborted();
      setReviewFilter(filter);
      setData((previous) => previous && { ...previous, findings });
    }, 'Temuan gagal dimuat.');
  }

  function showReport(template: 'executive' | 'technical', label: string) {
    setReport(undefined);
    void run(async (signal) => {
      const value = await request(`${path}/reports/${template}`, { signal }, session);
      signal.throwIfAborted();
      if (!isObject(value) || value.case_id !== caseId || value.mode !== 'SYNTHETIC' || value.template !== template) {
        throw new Error('Unexpected report');
      }
      setReport({ label, data: value });
    }, 'Laporan gagal dimuat.');
  }

  function review(event: FormEvent<HTMLFormElement>, finding: Finding) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void run(async (signal) => {
      await request(`${path}/findings/${finding.id}/review`, {
        method: 'PATCH',
        body: JSON.stringify({ verification: form.get('decision'), note: form.get('note'), expected: finding.verification }),
        signal,
      }, session);
      setReport(undefined);
      await refresh(signal);
    }, 'Keputusan review gagal disimpan.');
  }

  function changeCollaborator(username: string, method: 'PUT' | 'DELETE') {
    void run(async (signal) => {
      await request(`${path}/collaborators/${encodeURIComponent(username)}`, { method, signal }, session);
      await refresh(signal);
    }, 'Akses kolaborator gagal diubah.');
  }

  return (
    <section aria-label="Pekerjaan, review, dan laporan">
      <h3>Pekerjaan, review, dan laporan</h3>
      <fieldset disabled={busy}>
        <button type="button" onClick={() => void run(refresh, 'Aktivitas kasus gagal dimuat.')}>Muat aktivitas kasus</button>
        <button type="button" onClick={() => showReport('executive', 'Laporan eksekutif')}>Laporan eksekutif</button>
        {canReadTechnical &&
          <button type="button" onClick={() => showReport('technical', 'Laporan teknis')}>Laporan teknis</button>}
        {issue && <p role="alert">{issue.message} {issue.id && <code>{issue.id}</code>}</p>}
        {data && <>
          <h4>Antrean dan riwayat pekerjaan</h4>
          <p role="status">{data.jobs.items.length} dari {data.jobs.total} pekerjaan</p>
          {data.jobs.total === 0 && <p>Belum ada pekerjaan untuk kasus ini.</p>}
          <ul>{data.jobs.items.map((job) => {
            const sourceActions = job.status === 'queued' ? [['pause', 'Jeda'], ['cancel', 'Batalkan']]
              : job.status === 'paused' ? [...(open ? [['resume', 'Lanjutkan']] : []), ['cancel', 'Batalkan']]
              : job.status === 'failed' && open ? [['retry', 'Ulangi']] : [];
            const actions = job.kind === 'synthetic_source'
              ? (supervisor || analyst ? sourceActions : [])
              : examiner && open && job.status === 'failed' && job.consent_active ? [['retry', 'Ulangi mock scan']] : [];
            return <li key={job.id}><JobLine job={job} />{' '}
              {actions.map(([action, label]) =>
                <button key={action} type="button" onClick={() => void run(async (signal) => {
                  await request(`${path}/jobs/${job.id}?action=${action}`, { method: 'PATCH', signal }, session);
                  await refresh(signal);
                }, 'Pekerjaan gagal diubah.')}>{label}</button>)}
            </li>;
          })}</ul>
          {data.jobs.next && <button type="button" onClick={() => void run(async (signal) => {
            const jobs = await loadJobs(signal, data.jobs.next ?? undefined);
            signal.throwIfAborted();
            setData((previous) => previous && { ...previous, jobs: appendActivity(previous.jobs, jobs) });
          }, 'Pekerjaan berikutnya gagal dimuat.')}>Muat pekerjaan berikutnya</button>}
          {findingsPage && <>
            <h4>Review temuan sintetis</h4>
            <label>Status review
              <select value={reviewFilter} onChange={(event) => filterFindings(event.target.value as ReviewFilter)}>
                {Object.entries(reviewStatuses).map(([status, label]) => <option key={status} value={status}>{label}</option>)}
                <option value="all">Semua temuan</option>
              </select>
            </label>
            <p role="status">{findingsPage.items.length} dari {findingsPage.total} temuan</p>
            {findingsPage.total === 0 && <p>Belum ada temuan untuk filter ini.</p>}
            <ul>{findingsPage.items.map((finding) => {
              const evidence = finding.evidence;
              return <li key={finding.id}>
                <p><strong>{reviewStatuses[finding.verification]}</strong> · Indikator <code>{evidence.indicator}</code>
                  {' · '}Status ancaman {finding.threat_status} · Severity {finding.severity}</p>
                <p>Sumber <code>{evidence.source_ref}</code> · <time dateTime={evidence.observed_at}>{formatTimestamp(evidence.observed_at)}</time></p>
                <p>Impor <code>{evidence.import_id}</code> · SHA-256 <code>{evidence.import_sha256}</code></p>
                <p>SHA-256 temuan <code>{finding.evidence_sha256}</code> · {evidence.limitation}</p>
                {finding.review_note && <p>{finding.review_note}</p>}
                {finding.reviewed_by && <p>Peninjau <code>{finding.reviewed_by}</code>
                  {finding.reviewed_at && <> · <time dateTime={finding.reviewed_at}>{formatTimestamp(finding.reviewed_at)}</time></>}
                </p>}
                {canReview && finding.verification === 'pending' && <form onSubmit={(event) => review(event, finding)}>
                  <label>Keputusan
                    <select name="decision">
                      <option value="verified">Terverifikasi</option>
                      <option value="inconclusive">Tidak meyakinkan</option>
                      <option value="rejected">Ditolak</option>
                    </select>
                  </label>
                  <label>Catatan relevansi dan batasan <input name="note" maxLength={500} required /></label>
                  <button type="submit">Simpan keputusan</button>
                </form>}
              </li>;
            })}</ul>
            {findingsPage.next && <button type="button" onClick={() => void run(async (signal) => {
              const findings = await loadFindings(reviewFilter, signal, findingsPage.next ?? undefined);
              signal.throwIfAborted();
              setData((previous) => previous?.findings
                ? { ...previous, findings: appendActivity(previous.findings, findings) } : previous);
            }, 'Temuan berikutnya gagal dimuat.')}>Muat temuan berikutnya</button>}
          </>}
          <h4>Kolaborator kasus</h4>
          <ul>{data.collaborators.map((username) => <li key={username}>{username}{' '}
            {supervisor && open && <button type="button" onClick={() => changeCollaborator(username, 'DELETE')}>Cabut akses</button>}
          </li>)}</ul>
          {supervisor && open && <form onSubmit={(event) => {
            event.preventDefault();
            const username = new FormData(event.currentTarget).get('collaborator');
            if (typeof username === 'string') changeCollaborator(username, 'PUT');
          }}>
            <label>Nama pengguna kolaborator <input name="collaborator" required pattern="[a-z0-9][a-z0-9._\-]{0,63}" /></label>
            <button type="submit">Berikan akses</button>
          </form>}
        </>}
      </fieldset>
      {report && <section aria-label={report.label}>
        <h4>{report.label} · SINTETIS</h4>
        <pre className="workflow-report">{JSON.stringify(report.data, null, 2)}</pre>
      </section>}
    </section>
  );
}
