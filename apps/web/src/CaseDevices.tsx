import { useRef, useState } from 'react';
import { isUuid } from './api';
import { useOperatorTask } from './CaseWorkflow';
import { isTimestamp } from './contracts';
import { formatTimestamp } from './display';
import { isObject, request, type Session } from './operatorApi';

type Decision = 'granted' | 'declined';
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

export function CaseDevices(props: {
  caseId: string; open: boolean; session: Session; onSessionExpired: (id: string | null) => void;
}) {
  const { caseId, session, open } = props;
  const [devices, setDevices] = useState<Devices>();
  const { run, busy, issue } = useOperatorTask(props);
  const dialog = useRef<HTMLDialogElement>(null);
  const pendingDecision = useRef<{ key: string; decision: Decision }>(null);
  const path = `/cases/${caseId}/devices`;
  const examiner = session.roles.includes('forensic_examiner');
  const canRevoke = examiner || session.roles.includes('supervisor');

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

  function recordDecision(decision: Decision) {
    const key = pendingDecision.current?.decision === decision ? pendingDecision.current.key : crypto.randomUUID();
    pendingDecision.current = { key, decision };
    void run(async (signal) => {
      await request(path, {
        signal, method: 'POST', headers: { 'Idempotency-Key': key },
        body: JSON.stringify({ status: decision }),
      }, session);
      await refresh(signal);
      pendingDecision.current = null;
      dialog.current?.close();
    }, 'Keputusan persetujuan perangkat gagal disimpan.');
  }

  function updateDevice(id: string, action: 'jobs' | 'revoke') {
    void run(async (signal) => {
      await request(`${path}/${id}/${action}`, { method: 'POST', signal }, session);
      await refresh(signal);
    }, 'Sesi perangkat gagal diperbarui.');
  }

  return (
    <section aria-label="Simulasi USB">
      <h3>Simulasi USB</h3>
      <button type="button" disabled={busy} onClick={() => void run(refresh, 'Sesi perangkat gagal dimuat.')}>Muat sesi perangkat</button>
      {issue && <p role="alert">{issue.message} {issue.id && <code>{issue.id}</code>}</p>}
      {devices && <>
        <p>Profil {devices.platform === 'android' ? 'Android' : 'iPhone'} · {devices.scope}</p>
        {devices.platform === 'iphone' && <p>Diagnostik indikator ancaman tidak didukung pada profil iPhone.</p>}
        {examiner && open && <button type="button" disabled={busy} onClick={() => dialog.current?.showModal()}>Catat persetujuan simulasi</button>}
        <dialog ref={dialog} aria-label="Persetujuan simulasi perangkat">
          <h4>Persetujuan simulasi perangkat</h4>
          <p>{devices.disclosure}</p>
          <p>Lingkup {devices.scope}</p>
          {issue && <p role="alert">{issue.message} {issue.id && <code>{issue.id}</code>}</p>}
          <button type="button" disabled={busy} onClick={() => recordDecision('granted')}>Catat persetujuan</button>
          <button type="button" disabled={busy} onClick={() => recordDecision('declined')}>Catat penolakan</button>
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
        </li>)}</ul>
      </>}
    </section>
  );
}
