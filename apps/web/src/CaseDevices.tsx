import { useRef, useState } from 'react';
import { isUuid } from './api';
import { AuditEvents, isAuditEvent, type AuditEvent } from './AuditEvents';
import { useOperatorTask } from './CaseWorkflow';
import { isTimestamp } from './contracts';
import { formatTimestamp } from './display';
import { isObject, request, type Session } from './operatorApi';
import { isWriteRejection } from './pendingWrite';

type Decision = 'granted' | 'declined';
type ConsentAttempt = { key: string; decision: Decision };
type ConsentStatus = Decision | 'revoked';
type DeviceSession = {
  id: string; status: ConsentStatus; decided_at: string; revoked_at: string | null;
  job_id: string | null; evidence_sha256: string | null;
  evidence: { result: 'sample_available' | 'unsupported' } | null;
};
type Devices = { platform: 'android' | 'iphone'; scope: string; disclosure: string; sessions: DeviceSession[] };

const decisionLabels: Record<ConsentStatus, string> = {
  granted: 'Disetujui', declined: 'Ditolak', revoked: 'Dicabut',
};

function isDeviceSession(value: unknown): value is DeviceSession {
  return isObject(value) && isUuid(value.id) && isTimestamp(value.decided_at)
    && (value.status === 'granted' || value.status === 'declined' || value.status === 'revoked')
    && (value.revoked_at === null || isTimestamp(value.revoked_at))
    && (value.job_id === null || isUuid(value.job_id))
    && (value.evidence_sha256 === null || typeof value.evidence_sha256 === 'string')
    && (value.evidence === null || (isObject(value.evidence)
      && (value.evidence.result === 'sample_available' || value.evidence.result === 'unsupported')));
}

function readConsentAttempt(storageKey: string): ConsentAttempt | undefined {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null');
    if (isObject(value) && isUuid(value.key) && (value.decision === 'granted' || value.decision === 'declined')) {
      return { key: value.key, decision: value.decision };
    }
  } catch {
    return undefined;
  }
}

export function CaseDevices(props: {
  caseId: string; open: boolean; session: Session; onSessionExpired: (id: string | null) => void;
}) {
  const { caseId, session, open } = props;
  const [devices, setDevices] = useState<Devices>();
  const [audit, setAudit] = useState<{ sessionId: string; events: AuditEvent[] }>();
  const storageKey = `margono.pending-consent:${session.userId}:${caseId}`;
  const [pendingDecision, setPendingDecision] = useState(() => readConsentAttempt(storageKey));
  const [notice, setNotice] = useState('');
  const { run, busy, issue } = useOperatorTask(props);
  const dialog = useRef<HTMLDialogElement>(null);
  const path = `/cases/${caseId}/devices`;
  const examiner = session.roles.includes('forensic_examiner');
  const supervisor = session.roles.includes('supervisor');
  const canRevoke = examiner || supervisor;

  async function refresh(signal: AbortSignal) {
    const data = await request(path, { signal }, session);
    signal.throwIfAborted();
    if (!isObject(data) || data.mode !== 'SYNTHETIC'
        || (data.platform !== 'android' && data.platform !== 'iphone')
        || typeof data.scope !== 'string' || typeof data.disclosure !== 'string'
        || !Array.isArray(data.sessions) || !data.sessions.every(isDeviceSession)) {
      throw new Error('Unexpected device response');
    }
    setDevices({ platform: data.platform, scope: data.scope, disclosure: data.disclosure, sessions: data.sessions });
  }

  function clearDecision(attempt: ConsentAttempt) {
    if (readConsentAttempt(storageKey)?.key !== attempt.key) return;
    sessionStorage.removeItem(storageKey);
    setPendingDecision(undefined);
  }

  function recordDecision(decision: Decision | undefined, checkOnly = false) {
    setNotice('');
    void run(async (signal) => {
      let attempt = readConsentAttempt(storageKey);
      const recovering = Boolean(attempt);
      let saved: unknown = null;
      if (attempt) {
        saved = await request(`${path}/decision`, { signal, headers: { 'Idempotency-Key': attempt.key } }, session);
        signal.throwIfAborted();
        if (saved === null && (checkOnly || !open)) {
          setNotice(open ? 'Keputusan belum ditemukan. Coba lagi untuk mengirim keputusan yang sama.'
            : 'Keputusan belum ditemukan. Buka kembali kasus untuk mencoba lagi.');
          return;
        }
      } else {
        if (!decision || !open || checkOnly) return;
        attempt = { key: crypto.randomUUID(), decision };
        sessionStorage.setItem(storageKey, JSON.stringify(attempt));
        setPendingDecision(attempt);
      }
      if (saved === null) {
        const submitted = attempt;
        saved = await request(path, {
          signal, method: 'POST', headers: { 'Idempotency-Key': submitted.key },
          body: JSON.stringify({ status: submitted.decision }),
        }, session).catch((error: unknown) => {
          if (!recovering && !signal.aborted && isWriteRejection(error)) clearDecision(submitted);
          throw error;
        });
      }
      if (!isDeviceSession(saved)) throw new Error('Unexpected consent receipt');
      await refresh(signal);
      signal.throwIfAborted();
      clearDecision(attempt);
      setNotice(`Keputusan ${decisionLabels[saved.status].toLowerCase()} · ${saved.id}`);
      dialog.current?.close();
    }, 'Portal belum menerima hasil konfirmasi keputusan.');
  }

  function updateDevice(id: string, action: 'jobs' | 'revoke') {
    void run(async (signal) => {
      await request(`${path}/${id}/${action}`, { method: 'POST', signal }, session);
      signal.throwIfAborted();
      setAudit(undefined);
      await refresh(signal);
    }, 'Sesi perangkat gagal diperbarui.');
  }

  function readAudit(sessionId: string) {
    setAudit(undefined);
    void run(async (signal) => {
      const events = await request(`${path}/${sessionId}/audit`, { signal }, session);
      signal.throwIfAborted();
      if (!Array.isArray(events) || !events.every(isAuditEvent)) throw new Error('Unexpected consent audit');
      setAudit({ sessionId, events });
    }, 'Audit sesi perangkat gagal dimuat.');
  }

  return (
    <section aria-label="Simulasi USB">
      <h3>Simulasi USB</h3>
      <button type="button" disabled={busy} onClick={() => void run(refresh, 'Sesi perangkat gagal dimuat.')}>Muat sesi perangkat</button>
      {issue && <p role="alert">{issue.message} {issue.id && <code>{issue.id}</code>}</p>}
      <p className="operation-status" role="status">
        {notice || (examiner && pendingDecision && 'Hasil keputusan belum diketahui. Periksa keputusan sebelum mencoba lagi.')}
      </p>
      {examiner && pendingDecision && <>
        <button type="button" disabled={busy} onClick={() => recordDecision(undefined, true)}>Periksa keputusan</button>
        {open && <button type="button" disabled={busy} onClick={() => recordDecision(undefined)}>Coba lagi keputusan</button>}
      </>}
      {devices && <>
        <p>Profil {devices.platform === 'android' ? 'Android' : 'iPhone'} · {devices.scope}</p>
        {devices.platform === 'iphone' && <p>Diagnostik indikator ancaman tidak didukung pada profil iPhone.</p>}
        {examiner && open && !pendingDecision && <button type="button" disabled={busy} onClick={() => dialog.current?.showModal()}>Catat persetujuan simulasi</button>}
        <dialog ref={dialog} aria-label="Persetujuan simulasi perangkat">
          <h4>Persetujuan simulasi perangkat</h4>
          <p>{devices.disclosure}</p>
          <p>Lingkup {devices.scope}</p>
          {issue && <p role="alert">{issue.message} {issue.id && <code>{issue.id}</code>}</p>}
          {pendingDecision ? (
            <>
              <p role="status">Hasil keputusan belum diketahui. Periksa keputusan sebelum mencoba lagi.</p>
              <button type="button" disabled={busy} onClick={() => recordDecision(undefined, true)}>Periksa keputusan</button>
              {open && <button type="button" disabled={busy} onClick={() => recordDecision(undefined)}>Coba lagi keputusan</button>}
            </>
          ) : (
            <>
              <button type="button" disabled={busy} onClick={() => recordDecision('granted')}>Catat persetujuan</button>
              <button type="button" disabled={busy} onClick={() => recordDecision('declined')}>Catat penolakan</button>
            </>
          )}
          <button type="button" onClick={() => dialog.current?.close()}>Tutup dialog</button>
        </dialog>
        {devices.sessions.length === 0 && <p>Belum ada keputusan persetujuan.</p>}
        <ul>{devices.sessions.map((item) => <li key={item.id}>
          <p>{decisionLabels[item.status]} · <code>{item.id}</code> · <time dateTime={item.decided_at}>{formatTimestamp(item.decided_at)}</time></p>
          {item.revoked_at && <p>Dicabut <time dateTime={item.revoked_at}>{formatTimestamp(item.revoked_at)}</time></p>}
          {item.job_id && <p>Pekerjaan <code>{item.job_id}</code> dapat dilihat pada aktivitas kasus.</p>}
          {item.evidence && <p>{item.evidence.result === 'unsupported' ? 'Tidak didukung' : 'Metadata sintetis tersedia'}
            {' · '}SHA-256 <code>{item.evidence_sha256}</code>. Hasil simulasi tidak menentukan apakah perangkat aman.</p>}
          {examiner && open && item.status === 'granted' && !item.job_id &&
            <button type="button" disabled={busy} onClick={() => updateDevice(item.id, 'jobs')}>Antrekan mock scan</button>}
          {canRevoke && item.status === 'granted' &&
            <button type="button" disabled={busy} onClick={() => updateDevice(item.id, 'revoke')}>Cabut persetujuan</button>}
          {supervisor &&
            <button type="button" disabled={busy} onClick={() => readAudit(item.id)}>Periksa audit sesi</button>}
        </li>)}</ul>
        {audit && <section aria-label="Audit sesi perangkat">
          <h4>Audit sesi perangkat <code>{audit.sessionId}</code></h4>
          <AuditEvents events={audit.events} />
        </section>}
      </>}
    </section>
  );
}
