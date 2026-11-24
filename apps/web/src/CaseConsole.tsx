import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { isUuid } from './api';
import { CaseDevices } from './CaseDevices';
import { CaseImports } from './CaseImports';
import { CaseWorkflow, PortalJobs } from './CaseWorkflow';
import { isTimestamp, type SyntheticCase } from './contracts';
import { formatTimestamp, rememberSelection, selectionUrl } from './display';
import { isObject, operatorResponse, request, RequestError, type Session } from './operatorApi';
import { clearPendingWrite, readPendingWrite, savePendingWrite, writeFingerprint, type PendingWrite } from './pendingWrite';

type Case = {
  id: string; owner_id: string; synthetic_fixture_id: string; purpose: string;
  status: 'open' | 'closed'; created_at: string; closed_at: string | null;
};

function isCase(value: unknown): value is Case {
  return isObject(value) && isUuid(value.id) && isUuid(value.owner_id)
    && typeof value.synthetic_fixture_id === 'string' && typeof value.purpose === 'string'
    && (value.status === 'open' || value.status === 'closed')
    && isTimestamp(value.created_at) && (value.closed_at === null || isTimestamp(value.closed_at));
}

async function readCasePage(session: Session, before?: string) {
  const query = before ? `?before=${before}` : '';
  const response = await operatorResponse(`/cases${query}`, {}, session);
  const items: unknown = await response.json();
  const cursor = response.headers.get('X-Next-Cursor');
  if (!Array.isArray(items) || !items.every(isCase) || (cursor !== null && !isUuid(cursor))) {
    throw new Error('Unexpected case list');
  }
  return { items, cursor };
}

const caseRoles = ['osint_analyst', 'forensic_examiner'];
const creationStorageKey = (session: Session) => `margono.pending-case:${session.userId}`;

export function CaseConsole({ fixtures }: { fixtures: SyntheticCase[] }) {
  const [session, setSession] = useState<Session>();
  const [cases, setCases] = useState<Case[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [pendingCreation, setPendingCreation] = useState<PendingWrite>();
  const currentSession = useRef<Session>(null);
  const casePicker = useRef<HTMLSelectElement>(null);
  const loadMoreButton = useRef<HTMLButtonElement>(null);
  const restorePaginationFocus = useRef(false);
  const [selectedId, setSelectedId] = useState('');
  const [issue, setIssue] = useState('');
  const [issueId, setIssueId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const selected = selectedId ? cases.find((item) => item.id === selectedId) : cases[0];
  const deviceCase = fixtures.some((fixture) => fixture.case_id === selected?.synthetic_fixture_id && fixture.workspace === 'usb');

  useEffect(() => {
    function handlePop() {
      const id = new URLSearchParams(window.location.search).get('saved') ?? '';
      if (id === selectedId) return;
      setSelectedId(id);
    }
    window.addEventListener('popstate', handlePop);
    return () => window.removeEventListener('popstate', handlePop);
  }, [selectedId]);

  useEffect(() => {
    if (busy || !restorePaginationFocus.current) return;
    restorePaginationFocus.current = false;
    const target = cursor ? loadMoreButton.current : casePicker.current;
    target?.focus();
  }, [busy, cursor]);

  const clearSession = useCallback(() => {
    currentSession.current = null;
    setSession(undefined);
    setCases([]);
    setCursor(null);
    setPendingCreation(undefined);
    restorePaginationFocus.current = false;
    setSelectedId('');
  }, []);

  const expireSession = useCallback((correlationId: string | null) => {
    clearSession();
    setIssue('Sesi telah berakhir. Silakan masuk kembali.');
    setIssueId(correlationId);
  }, [clearSession]);

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setIssue('');
    setIssueId(null);
    try {
      await action();
    } catch (error) {
      if (error instanceof RequestError) setIssueId(error.correlationId);
      if (error instanceof RequestError && error.status === 401) {
        clearSession();
        setIssue('Kredensial tidak valid atau sesi telah berakhir.');
      } else if (error instanceof RequestError && error.status === 503) {
        setIssue('Database lokal belum tersedia.');
      } else if (error instanceof RequestError && error.status === 422) {
        setIssue('Periksa format dan isian formulir.');
      } else if (error instanceof RequestError && error.status === 409) {
        setIssue('Operasi berbenturan dengan status kasus atau kunci impor.');
      } else {
        setIssue('Operasi gagal. Coba lagi.');
      }
    } finally {
      setBusy(false);
    }
  }

  function updateCase(value: unknown) {
    if (!isCase(value)) throw new Error('Unexpected case response');
    setCases((previous) => [value, ...previous.filter((item) => item.id !== value.id)]);
    setSelectedId(value.id);
    rememberSelection('saved', value.id);
  }

  function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    event.currentTarget.reset();
    void perform(async () => {
      const value = await request('/sessions', {
        method: 'POST', body: JSON.stringify({ username: fields.get('username'), password: fields.get('password') }),
      });
      if (!isObject(value) || typeof value.token !== 'string' || typeof value.user_id !== 'string'
        || !Array.isArray(value.roles) || !value.roles.every((role) => typeof role === 'string')) {
        throw new Error('Unexpected session response');
      }
      const next = { token: value.token, userId: value.user_id, roles: value.roles };
      if (next.roles.some((role) => caseRoles.includes(role) || role === 'supervisor')) {
        const { items, cursor } = await readCasePage(next);
        setCases(items);
        setCursor(cursor);
        const linked = new URLSearchParams(window.location.search).get('saved');
        if (isUuid(linked)) {
          setSelectedId(linked);
          const known = items.find((item) => item.id === linked);
          if (!known) {
            try {
              const linkedCase = await request(`/cases/${linked}`, {}, next);
              if (!isCase(linkedCase)) throw new Error('Unexpected case');
              updateCase(linkedCase);
            } catch (error) {
              if (error instanceof RequestError && error.status === 401) throw error;
              if (error instanceof RequestError) setIssueId(error.correlationId);
              setIssue('Kasus pada tautan tidak dapat dibuka.');
            }
          }
        }
      }
      currentSession.current = next;
      setPendingCreation(readPendingWrite(creationStorageKey(next)));
      setSession(next);
    });
  }

  function createCase(event: FormEvent<HTMLFormElement>, active: Session) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const purpose = fields.get('purpose');
    const scope = fields.get('scope');
    const body = purpose && scope ? JSON.stringify({ fixture_id: fields.get('fixture'), purpose, scope }) : undefined;
    const storageKey = creationStorageKey(active);
    void perform(async () => {
      let attempt = readPendingWrite(storageKey);
      let current: unknown = null;
      if (attempt) {
        current = await request('/cases/creation-receipt', { headers: { 'Idempotency-Key': attempt.key } }, active);
      }
      if (currentSession.current !== active) return;
      if (current === null) {
        if (!body) {
          setIssue('Hasil belum tercatat. Pilih fixture dan isi kembali tujuan serta ruang lingkup yang sama untuk mencoba lagi.');
          return;
        }
        const fingerprint = await writeFingerprint(body);
        if (currentSession.current !== active) return;
        if (attempt && attempt.fingerprint !== fingerprint) {
          setIssue('Isian berbeda dari permintaan sebelumnya. Gunakan isian yang sama atau mulai pembuatan baru.');
          return;
        }
        if (!attempt) {
          attempt = { key: crypto.randomUUID(), fingerprint };
          savePendingWrite(storageKey, attempt);
          setPendingCreation(attempt);
        }
        const receipt = await request('/cases', {
          method: 'POST', body, headers: { 'Idempotency-Key': attempt.key },
        }, active);
        if (!isCase(receipt)) throw new Error('Unexpected case receipt');
        current = await request(`/cases/${receipt.id}`, {}, active);
        if (!isCase(current) || current.id !== receipt.id) throw new Error('Unexpected current case');
      }
      if (currentSession.current !== active) return;
      if (!isCase(current) || current.owner_id !== active.userId || !attempt) throw new Error('Unexpected case recovery');
      if (!clearPendingWrite(storageKey, attempt)) return;
      setPendingCreation(undefined);
      updateCase(current);
      form.reset();
    });
  }

  function startNewCase(active: Session, pending: PendingWrite) {
    if (!clearPendingWrite(creationStorageKey(active), pending)) return;
    setPendingCreation(undefined);
    setIssue('');
    setIssueId(null);
  }

  function moreCases(active: Session) {
    if (!cursor) return;
    restorePaginationFocus.current = true;
    void perform(async () => {
      const next = await readCasePage(active, cursor);
      setCases((previous) => {
        const known = new Set(previous.map((item) => item.id));
        return [...previous, ...next.items.filter((item) => !known.has(item.id))];
      });
      setCursor(next.cursor);
    });
  }

  return (
    <section className="message system-status case-console" aria-labelledby="case-console-label">
      <h2 id="case-console-label">Kasus simulasi tersimpan</h2>
      <p>Gunakan akun operator lokal dan data sintetis.</p>
      {issue && <p role="alert">{issue}</p>}
      {issue && issueId && <p>ID korelasi <code>{issueId}</code></p>}
      {!session ? (
        <form onSubmit={login}>
          <fieldset disabled={busy}>
            <label>Nama pengguna <input name="username" autoComplete="username" required maxLength={64} /></label>
            <label>Kata sandi <input name="password" type="password" autoComplete="current-password" required maxLength={256} /></label>
            <button type="submit">Masuk</button>
          </fieldset>
        </form>
      ) : (
        <fieldset disabled={busy}>
          <button type="button" onClick={() => void perform(async () => {
            await request('/sessions/current', { method: 'DELETE' }, session);
            clearSession();
          })}>Keluar</button>
          {session.roles.some((role) => caseRoles.includes(role)) && fixtures.length > 0 && (
            <form onSubmit={(event) => createCase(event, session)}>
              <label>Fixture kasus
                <select name="fixture" required>
                  {fixtures.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {item.label}</option>)}
                </select>
              </label>
              <label>Tujuan <input name="purpose" maxLength={500} required /></label>
              <label>Ruang lingkup <input name="scope" maxLength={500} required /></label>
              {pendingCreation ? (
                <>
                  <p role="status">Hasil pembuatan sebelumnya belum diketahui. Mulai pembuatan baru hanya jika Anda memang ingin membuat kasus lain.</p>
                  <button type="submit" formNoValidate>Coba lagi pembuatan kasus</button>
                  <button type="button" onClick={() => startNewCase(session, pendingCreation)}>Mulai pembuatan baru</button>
                </>
              ) : <button type="submit">Buat kasus</button>}
            </form>
          )}
          {cases.length > 0 && (
            <label>Kasus tersimpan
              <select ref={casePicker} value={selected?.id ?? ''} onChange={(event) => {
                setSelectedId(event.target.value);
                rememberSelection('saved', event.target.value);
                setIssue('');
                setIssueId(null);
              }}>
                <option value="" disabled>Pilih kasus</option>
                {cases.map((item) => <option key={item.id} value={item.id}>{item.synthetic_fixture_id} · {item.purpose}</option>)}
              </select>
            </label>
          )}
          {cursor && <button ref={loadMoreButton} type="button" onClick={() => moreCases(session)}>Muat kasus sebelumnya</button>}
          {selected ? (
            <>
              <p><a href={selectionUrl('saved', selected.id).href}>Tautan kasus tersimpan</a></p>
              <p>Waktu dibuat <time dateTime={selected.created_at}>{formatTimestamp(selected.created_at)}</time></p>
              {selected.closed_at && (
                <p>Waktu ditutup <time dateTime={selected.closed_at}>{formatTimestamp(selected.closed_at)}</time></p>
              )}
              <p>Status kasus <strong>{selected.status === 'open' ? 'Terbuka' : 'Ditutup'}</strong></p>
              {session.roles.includes('supervisor') && (
                <button type="button" onClick={() => void perform(async () => {
                  const status = selected.status === 'open' ? 'closed' : 'open';
                  updateCase(await request(`/cases/${selected.id}/status?status=${status}`, { method: 'PATCH' }, session));
                })}>{selected.status === 'open' ? 'Tutup kasus' : 'Buka kembali kasus'}</button>
              )}
              <CaseImports
                key={`imports:${selected.id}`}
                caseId={selected.id}
                session={session}
                canManageImports={session.roles.includes('osint_analyst') && selected.owner_id === session.userId}
                caseOpen={selected.status === 'open'}
                onSessionExpired={expireSession}
              />
              {deviceCase &&
                <CaseDevices key={`devices:${selected.id}`} caseId={selected.id} open={selected.status === 'open'}
                  session={session} onSessionExpired={expireSession} />}
              <CaseWorkflow key={`workflow:${selected.id}`} deviceCase={deviceCase} caseId={selected.id} open={selected.status === 'open'}
                session={session} onSessionExpired={expireSession} />
            </>
          ) : cases.length === 0 && <p>Belum ada kasus yang dapat Anda akses.</p>}
        </fieldset>
      )}
    </section>
  );
}
