import { useState, type FormEvent } from 'react';
import type { SyntheticCase } from './contracts';

type Session = { token: string; userId: string; roles: string[] };
type Case = { id: string; owner_id: string; synthetic_fixture_id: string; purpose: string; status: 'open' | 'closed' };
type PreviewRow = {
  row_number: number;
  reference_label: string | null;
  status: 'valid' | 'invalid';
  duplicate: boolean;
};
type ImportPayload = { content: string; column: string };
type InputPreview = { payload: ImportPayload; rows: PreviewRow[]; key: string };

class RequestError extends Error {
  constructor(readonly status: number) { super('Operator request failed'); }
}

async function request(path: string, options: RequestInit = {}, session?: Session): Promise<unknown> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (session) headers.set('Authorization', `Bearer ${session.token}`);
  const response = await fetch(`/api/v1${path}`, {
    ...options, headers, cache: 'no-store', signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new RequestError(response.status);
  return response.status === 204 ? null : response.json();
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCase(value: unknown): value is Case {
  return isObject(value) && typeof value.id === 'string' && typeof value.owner_id === 'string'
    && typeof value.synthetic_fixture_id === 'string' && typeof value.purpose === 'string'
    && (value.status === 'open' || value.status === 'closed');
}

function isPreviewRow(value: unknown): value is PreviewRow {
  return isObject(value) && typeof value.row_number === 'number'
    && (typeof value.reference_label === 'string' || value.reference_label === null)
    && (value.status === 'valid' || value.status === 'invalid') && typeof value.duplicate === 'boolean';
}

const caseRoles = ['osint_analyst', 'forensic_examiner'];

export function CaseConsole({ fixtures }: { fixtures: SyntheticCase[] }) {
  const [session, setSession] = useState<Session>();
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [inspection, setInspection] = useState<InputPreview>();
  const [result, setResult] = useState('');
  const [issue, setIssue] = useState('');
  const [busy, setBusy] = useState(false);
  const selected = cases.find((item) => item.id === selectedId) ?? cases[0];

  function resetImport() {
    setInspection(undefined);
    setResult('');
  }

  function clearSession() {
    setSession(undefined);
    setCases([]);
    setSelectedId('');
    resetImport();
  }

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setIssue('');
    try {
      await action();
    } catch (error) {
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
    resetImport();
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
        const data = await request('/cases', {}, next);
        if (!Array.isArray(data) || !data.every(isCase)) throw new Error('Unexpected case list');
        setCases(data);
      }
      setSession(next);
    });
  }

  function createCase(event: FormEvent<HTMLFormElement>, active: Session) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    void perform(async () => {
      updateCase(await request('/cases', {
        method: 'POST',
        body: JSON.stringify({ fixture_id: fields.get('fixture'), purpose: fields.get('purpose'), scope: fields.get('scope') }),
      }, active));
      form.reset();
    });
  }

  function previewImport(event: FormEvent<HTMLFormElement>, active: Session, current: Case) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const file = fields.get('file');
    setInspection(undefined);
    setResult('');
    if (!(file instanceof File) || !file.size || file.size > 65_536) {
      setIssue('Pilih CSV UTF-8 dengan ukuran hingga 64 KiB.');
      return;
    }
    void perform(async () => {
      const content = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
      const payload = { content, column: String(fields.get('column')) };
      const result = await request(`/cases/${current.id}/imports/preview`, {
        method: 'POST', body: JSON.stringify(payload),
      }, active);
      if (!isObject(result) || !Array.isArray(result.rows) || !result.rows.every(isPreviewRow)) {
        throw new Error('Unexpected preview response');
      }
      setInspection({ payload, rows: result.rows, key: crypto.randomUUID() });
    });
  }

  return (
    <section className="message system-status case-console" aria-labelledby="case-console-label">
      <h2 id="case-console-label">Kasus simulasi tersimpan</h2>
      <p>Gunakan akun operator lokal dan data sintetis.</p>
      {issue && <p role="alert">{issue}</p>}
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
              <button type="submit">Buat kasus</button>
            </form>
          )}
          {selected ? (
            <>
              <label>Kasus tersimpan
                <select value={selected.id} onChange={(event) => {
                  setSelectedId(event.target.value);
                  resetImport();
                }}>
                  {cases.map((item) => <option key={item.id} value={item.id}>{item.synthetic_fixture_id} · {item.purpose}</option>)}
                </select>
              </label>
              <p>Status kasus <strong>{selected.status === 'open' ? 'Terbuka' : 'Ditutup'}</strong></p>
              {session.roles.includes('supervisor') && (
                <button type="button" onClick={() => void perform(async () => {
                  const status = selected.status === 'open' ? 'closed' : 'open';
                  updateCase(await request(`/cases/${selected.id}/status?status=${status}`, { method: 'PATCH' }, session));
                })}>{selected.status === 'open' ? 'Tutup kasus' : 'Buka kembali kasus'}</button>
              )}
              {session.roles.includes('osint_analyst') && selected.owner_id === session.userId && selected.status === 'open' && (
                <form onSubmit={(event) => previewImport(event, session, selected)} onChange={resetImport}>
                  <label>CSV sintetis <input name="file" type="file" accept=".csv,text/csv" required /></label>
                  <label>Kolom label <input name="column" defaultValue="Nama" maxLength={128} required /></label>
                  <button type="submit">Pratinjau CSV</button>
                </form>
              )}
              {inspection && (
                <>
                  <ul aria-label="Pratinjau baris CSV">
                    {inspection.rows.map((row) => (
                      <li key={row.row_number}>
                        {row.row_number} · {row.reference_label ?? 'Label kosong atau tidak valid'} · {row.status}
                        {row.duplicate && ' · Duplikat'}
                      </li>
                    ))}
                  </ul>
                  <button type="button" onClick={() => void perform(async () => {
                    const saved = await request(`/cases/${selected.id}/imports`, {
                      method: 'POST',
                      headers: { 'Idempotency-Key': inspection.key },
                      body: JSON.stringify(inspection.payload),
                    }, session);
                    if (!isObject(saved) || typeof saved.row_count !== 'number') throw new Error('Unexpected import result');
                    setResult(`${saved.row_count} baris tersimpan.`);
                    setInspection(undefined);
                  })}>Konfirmasi impor</button>
                </>
              )}
              {result && <p role="status">{result}</p>}
            </>
          ) : <p>Belum ada kasus yang dapat Anda akses.</p>}
        </fieldset>
      )}
    </section>
  );
}
