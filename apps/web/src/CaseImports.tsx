import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { isUuid } from './api';
import { isTimestamp } from './contracts';
import { formatTimestamp } from './display';
import { isObject, operatorResponse, request, RequestError, type Session } from './operatorApi';
import { clearPendingWrite, isWriteRejection, readPendingWrite, savePendingWrite, writeFingerprint, type PendingWrite } from './pendingWrite';

type Counts = { row_count: number; valid_count: number; invalid_count: number };
type Result = Counts & { id: string; sha256: string };
type ImportFormat = 'csv' | 'xlsx' | 'manual';
type ImportInput = { content: string; format: ImportFormat };
type Summary = Counts & { id: string; created_at: string; selected_column: string | null; sha256: string | null; source_format?: ImportFormat };
type History = { items: Summary[]; next_cursor: string | null };
type PreviewRow = {
  row_number: number;
  reference_label: string | null;
  status: 'valid' | 'invalid';
  duplicate: boolean;
};
type Inspection = {
  caseId: string;
  payload: ImportInput & { column: string };
  rows: PreviewRow[];
};
type BatchDetails = {
  id: string;
  rows: Array<{ row_number: number; reference_label: string | null; status: string; duplicate: boolean }>;
  events: Array<{ action: string; occurred_at: string; correlation_id: string | null }>;
};

function isBatchRow(value: unknown): value is BatchDetails['rows'][number] {
  return isObject(value) && typeof value.row_number === 'number'
    && (value.reference_label === null || typeof value.reference_label === 'string')
    && typeof value.status === 'string' && typeof value.duplicate === 'boolean';
}

function isBatchEvent(value: unknown): value is BatchDetails['events'][number] {
  return isObject(value) && typeof value.action === 'string' && isTimestamp(value.occurred_at)
    && (value.correlation_id === null || isUuid(value.correlation_id));
}

type Issue = { message: string; correlationId?: string | null };

function isCounts(value: unknown): value is Counts {
  return isObject(value) && typeof value.row_count === 'number'
    && typeof value.valid_count === 'number' && typeof value.invalid_count === 'number';
}

function isResult(value: unknown): value is Result {
  return isObject(value) && isUuid(value.id) && typeof value.sha256 === 'string' && isCounts(value);
}

function isSummary(value: unknown): value is Summary {
  return isObject(value) && isUuid(value.id) && isTimestamp(value.created_at)
    && (value.selected_column === null || typeof value.selected_column === 'string')
    && (value.sha256 === null || typeof value.sha256 === 'string')
    && (value.source_format === undefined || value.source_format === 'csv'
      || value.source_format === 'xlsx' || value.source_format === 'manual') && isCounts(value);
}

function isPreviewRow(value: unknown): value is PreviewRow {
  return isObject(value) && typeof value.row_number === 'number'
    && (typeof value.reference_label === 'string' || value.reference_label === null)
    && (value.status === 'valid' || value.status === 'invalid') && typeof value.duplicate === 'boolean';
}

async function loadHistory(path: string, session: Session, signal: AbortSignal): Promise<History> {
  const data = await request(path, { signal }, session);
  if (!isObject(data) || !Array.isArray(data.items) || !data.items.every(isSummary)
      || (data.next_cursor !== null && !isUuid(data.next_cursor))) {
    throw new Error('Unexpected import history');
  }
  return { items: data.items, next_cursor: data.next_cursor };
}

async function loadConfirmation(path: string, key: string, session: Session, signal: AbortSignal) {
  const result = await request(`${path}/confirmation`, {
    headers: { 'Idempotency-Key': key }, signal,
  }, session);
  if (result !== null && !isResult(result)) throw new Error('Unexpected import confirmation');
  return result;
}

function importIssue(error: unknown, fallback: string): Issue {
  if (!(error instanceof RequestError)) return { message: fallback };
  const message = error.status === 422 ? 'Periksa format impor atau pilihan kolom.'
    : error.status === 403 || error.status === 404 ? 'Kasus atau impor ini tidak dapat diakses.'
    : error.status === 409 ? 'Impor tidak dapat diproses untuk status kasus atau kunci ini.' : fallback;
  return { message, correlationId: error.correlationId };
}

function CountsSummary({ counts }: { counts: Counts }) {
  const pending = counts.row_count - counts.valid_count - counts.invalid_count;
  return <>{counts.valid_count} valid, {counts.invalid_count} tidak valid{pending > 0 && `, ${pending} menunggu`}</>;
}

export function CaseImports({ caseId, session, canManageImports, caseOpen, onSessionExpired }: {
  caseId: string;
  session: Session;
  canManageImports: boolean;
  caseOpen: boolean;
  onSessionExpired: (correlationId: string | null) => void;
}) {
  const path = `/cases/${caseId}/imports`;
  const storageKey = `margono.pending-import:${session.userId}:${caseId}`;
  const canImport = canManageImports && caseOpen;
  const lifetime = useRef<AbortController>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState(() => readPendingWrite(storageKey));
  const [confirmationNotice, setConfirmationNotice] = useState('');
  const [file, setFile] = useState<ImportInput & { columns: string[] }>();
  const [manual, setManual] = useState('');
  const [column, setColumn] = useState('');
  const [inspection, setInspection] = useState<Inspection>();
  const [result, setResult] = useState<Result>();
  const [details, setDetails] = useState<BatchDetails>();
  const [submittedJobs, setSubmittedJobs] = useState<Record<string, string>>({});
  const [issue, setIssue] = useState<Issue>();
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<History>();
  const [historyIssue, setHistoryIssue] = useState<Issue>();
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const visibleInspection = inspection?.caseId === caseId ? inspection : undefined;

  const finishConfirmation = useCallback((attempt: PendingWrite, saved: Result) => {
    if (!clearPendingWrite(storageKey, attempt)) return;
    setPendingConfirmation(undefined);
    setConfirmationNotice('');
    setResult(saved);
    setInspection(undefined);
    setIssue(undefined);
    setHistoryAttempt((previous) => previous + 1);
  }, [storageKey]);

  useLayoutEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, [caseId, session]);

  useEffect(() => {
    const controller = new AbortController();
    setHistoryIssue(undefined);
    void loadHistory(path, session, controller.signal).then((data) => {
      if (!controller.signal.aborted) setHistory(data);
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      if (error instanceof RequestError && error.status === 401) onSessionExpired(error.correlationId);
      else setHistoryIssue(importIssue(error, 'Riwayat impor gagal dimuat.'));
    });
    return () => controller.abort();
  }, [path, session, historyAttempt, onSessionExpired]);

  useEffect(() => {
    const attempt = canManageImports && readPendingWrite(storageKey);
    if (!attempt) return;
    const controller = new AbortController();
    const { signal } = controller;
    void loadConfirmation(path, attempt.key, session, signal).then((saved) => {
      if (!signal.aborted && saved) finishConfirmation(attempt, saved);
    }).catch((error: unknown) => {
      if (signal.aborted || readPendingWrite(storageKey)?.key !== attempt.key) return;
      if (error instanceof RequestError && error.status === 401) onSessionExpired(error.correlationId);
      else setIssue(importIssue(error, 'Hasil konfirmasi sebelumnya gagal diperiksa. Coba lagi.'));
    });
    return () => controller.abort();
  }, [canManageImports, finishConfirmation, onSessionExpired, path, session, storageKey]);

  async function perform(action: (signal: AbortSignal) => Promise<void>, fallback: string) {
    const signal = lifetime.current?.signal;
    if (!signal || signal.aborted) return;
    setBusy(true);
    setIssue(undefined);
    try {
      await action(signal);
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof RequestError && error.status === 401) onSessionExpired(error.correlationId);
      else setIssue(importIssue(error, fallback));
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>, format: 'csv' | 'xlsx') {
    const selected = event.target.files?.[0];
    setFile(undefined);
    setColumn('');
    setInspection(undefined);
    setResult(undefined);
    setIssue(undefined);
    if (!selected) return;
    if (!selected.size || selected.size > 65_536) {
      setIssue({ message: 'Pilih CSV UTF-8 atau XLSX dengan ukuran hingga 64 KiB.' });
      return;
    }
    void perform(async (signal) => {
      const bytes = new Uint8Array(await selected.arrayBuffer());
      const content = format === 'csv'
        ? new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes)
        : btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join(''));
      const payload: ImportInput = { content, format };
      signal.throwIfAborted();
      const data = await request(`${path}/columns`, {
        method: 'POST', body: JSON.stringify(payload), signal,
      }, session);
      signal.throwIfAborted();
      if (!isObject(data) || !Array.isArray(data.columns) || !data.columns.every((value) => typeof value === 'string')) {
        throw new Error('Unexpected column response');
      }
      const columns = data.columns.filter((name: string) => name.length <= 128);
      if (!columns.length) throw new Error('No selectable column');
      setFile({ ...payload, columns });
      setColumn(columns.includes('Nama') ? 'Nama' : columns[0]);
    }, 'Kolom gagal dibaca. Pilih lembar kerja dengan header yang valid.');
  }

  function preview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (file && column) previewPayload({ content: file.content, format: file.format, column });
  }

  function previewManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const labels = manual.split(/\r\n|\r|\n/).map((line) => `"${line.replaceAll('"', '""')}"`);
    previewPayload({ content: ['Nama', ...labels].join('\n'), column: 'Nama', format: 'manual' });
  }

  function previewPayload(payload: Inspection['payload']) {
    setInspection(undefined);
    setResult(undefined);
    void perform(async (signal) => {
      const data = await request(`${path}/preview`, { method: 'POST', body: JSON.stringify(payload), signal }, session);
      signal.throwIfAborted();
      if (!isObject(data) || !Array.isArray(data.rows) || !data.rows.every(isPreviewRow)) {
        throw new Error('Unexpected preview response');
      }
      setInspection({ caseId, payload, rows: data.rows });
    }, 'Pratinjau impor gagal dimuat.');
  }

  function confirm(checkOnly = false) {
    if (!canManageImports) return;
    const body = visibleInspection && JSON.stringify(visibleInspection.payload);
    setConfirmationNotice('');
    void perform(async (signal) => {
      let attempt = readPendingWrite(storageKey);
      const recovering = Boolean(attempt);
      if (attempt) {
        const saved = await loadConfirmation(path, attempt.key, session, signal);
        signal.throwIfAborted();
        if (readPendingWrite(storageKey)?.key !== attempt.key) return;
        if (saved) {
          finishConfirmation(attempt, saved);
          return;
        }
      }
      if (checkOnly) {
        setConfirmationNotice('Hasil konfirmasi belum ditemukan di riwayat. Periksa lagi atau coba ulang dengan impor yang sama.');
        return;
      }
      if (!canImport || !body) {
        setIssue({ message: canImport
          ? 'Hasil belum tercatat. Pratinjau kembali file atau label yang sama sebelum mencoba lagi.'
          : 'Hasil belum tercatat. Kasus harus dibuka kembali untuk mengirim konfirmasi.' });
        return;
      }
      const fingerprint = await writeFingerprint(body);
      signal.throwIfAborted();
      if (attempt && attempt.fingerprint !== fingerprint) {
        setIssue({ message: 'Impor berbeda dari konfirmasi sebelumnya. Gunakan file dan kolom yang sama atau mulai impor baru.' });
        return;
      }
      if (attempt && readPendingWrite(storageKey)?.key !== attempt.key) return;
      if (!attempt) {
        attempt = { key: crypto.randomUUID(), fingerprint };
        savePendingWrite(storageKey, attempt);
        setPendingConfirmation(attempt);
      }
      const submitted = attempt;
      const data = await request(path, {
        method: 'POST', headers: { 'Idempotency-Key': submitted.key }, body, signal,
      }, session).catch((error: unknown) => {
        if (!recovering && isWriteRejection(error) && clearPendingWrite(storageKey, submitted)
            && !signal.aborted) setPendingConfirmation(undefined);
        throw error;
      });
      signal.throwIfAborted();
      if (!isResult(data)) throw new Error('Unexpected import result');
      finishConfirmation(attempt, data);
    }, checkOnly ? 'Riwayat konfirmasi belum dapat diperiksa.' : 'Portal belum menerima respons konfirmasi yang dapat dibaca.');
  }

  function startNewImport(attempt: PendingWrite) {
    if (!clearPendingWrite(storageKey, attempt)) return;
    setPendingConfirmation(undefined);
    setConfirmationNotice('');
    setIssue(undefined);
  }

  function more() {
    const cursor = history?.next_cursor;
    if (!cursor) return;
    void perform(async (signal) => {
      const next = await loadHistory(`${path}?before=${cursor}`, session, signal);
      signal.throwIfAborted();
      setHistory((previous) => ({
        items: [...(previous?.items ?? []), ...next.items],
        next_cursor: next.next_cursor,
      }));
    }, 'Halaman riwayat berikutnya gagal dimuat.');
  }

  function readBatch(id: string) {
    setDetails(undefined);
    void perform(async (signal) => {
      const data = await request(`${path}/${id}/details`, { signal }, session);
      signal.throwIfAborted();
      if (!isObject(data) || !Array.isArray(data.rows) || !data.rows.every(isBatchRow)
          || !Array.isArray(data.events) || !data.events.every(isBatchEvent)) throw new Error('Unexpected import details');
      setDetails({ id, rows: data.rows, events: data.events });
    }, 'Rincian batch gagal dimuat.');
  }

  function queue(id: string) {
    void perform(async (signal) => {
      const data = await request(`${path}/${id}/jobs`, {
        method: 'POST', headers: { 'Idempotency-Key': `source:${id}` }, signal,
      }, session);
      signal.throwIfAborted();
      if (!isObject(data) || !isUuid(data.id) || data.case_id !== caseId || data.import_id !== id) {
        throw new Error('Unexpected job response');
      }
      const jobId = data.id;
      setSubmittedJobs((previous) => ({ ...previous, [id]: jobId }));
    }, 'Pekerjaan sumber sintetis gagal ditambahkan.');
  }

  function download(id: string, format?: ImportFormat) {
    void perform(async (signal) => {
      const response = await operatorResponse(`${path}/${id}/evidence`, { signal }, session);
      const data = await response.blob();
      signal.throwIfAborted();
      const url = URL.createObjectURL(data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `bukti-${id}.${format === 'xlsx' ? 'xlsx' : 'csv'}.bin`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, 'Bukti impor gagal diunduh.');
  }

  return (
    <section aria-label="Impor label">
      <fieldset disabled={busy}>
        {issue && <p role="alert">{issue.message} {issue.correlationId && <code>{issue.correlationId}</code>}</p>}
        <div className="operation-status" id="import-confirmation-status" role="status">
          {canManageImports && pendingConfirmation && (
            <p>{confirmationNotice || (busy
              ? 'Menunggu respons konfirmasi…'
              : 'Hasil konfirmasi belum diketahui. Batch mungkin sudah tersimpan. Periksa riwayat sebelum mencoba lagi.')}</p>
          )}
          {result && (
            <>
              <p>{result.row_count} baris tersimpan. <CountsSummary counts={result} />.</p>
              <p>Import ID <code>{result.id}</code></p>
            </>
          )}
        </div>
        {canImport && (
          <>
          <form onSubmit={preview}>
            <label>CSV sintetis <input type="file" accept=".csv,text/csv" onChange={(event) => chooseFile(event, 'csv')} /></label>
            <label>XLSX sintetis <input type="file" accept=".xlsx" onChange={(event) => chooseFile(event, 'xlsx')} /></label>
            {file && (
              <label>Kolom label
                <select value={column} onChange={(event) => {
                  setColumn(event.target.value);
                  setInspection(undefined);
                  setResult(undefined);
                }}>
                  {file.columns.map((name) => <option key={name}>{name}</option>)}
                </select>
              </label>
            )}
            <button type="submit" disabled={!file}>{file?.format === 'xlsx' ? 'Pratinjau XLSX' : 'Pratinjau CSV'}</button>
          </form>
          <form onSubmit={previewManual}>
            <label>Label manual, satu per baris <textarea value={manual} onChange={(event) => {
              setManual(event.target.value);
              setInspection(undefined);
              setResult(undefined);
            }} rows={3} maxLength={32_000} required /></label>
            <button type="submit">Pratinjau label manual</button>
          </form>
          </>
        )}
        {canImport && visibleInspection && (
          <>
            <ul aria-label="Pratinjau baris impor">
              {visibleInspection.rows.map((row) => (
                <li key={row.row_number}>
                  {row.row_number} · {row.reference_label ?? 'Label kosong atau tidak valid'} · {row.status === 'valid' ? 'valid' : 'tidak valid'}
                  {row.duplicate && ' · Duplikat'}
                </li>
              ))}
            </ul>
            {!pendingConfirmation && <button type="button" onClick={() => confirm()}>Konfirmasi impor</button>}
          </>
        )}
        {canManageImports && pendingConfirmation && (
          <>
            <button type="button" aria-describedby="import-confirmation-status" onClick={() => confirm(true)}>Periksa riwayat konfirmasi</button>
            <button type="button" onClick={() => confirm()}>Coba lagi konfirmasi impor</button>
            {canImport && <button type="button" onClick={() => startNewImport(pendingConfirmation)}>Mulai impor baru</button>}
          </>
        )}
        <h3>Riwayat impor</h3>
        {!history && !historyIssue && <p role="status">Memuat riwayat impor…</p>}
        {historyIssue && (
          <p role="status">
            {historyIssue.message} {historyIssue.correlationId && <code>{historyIssue.correlationId}</code>}{' '}
            <button type="button" onClick={() => setHistoryAttempt((value) => value + 1)}>Muat ulang riwayat</button>
          </p>
        )}
        {history?.items.length === 0 && <p>Belum ada impor untuk kasus ini.</p>}
        {history && history.items.length > 0 && (
          <ul aria-label="Riwayat impor kasus">
            {history.items.map((item) => (
              <li key={item.id}>
                <time dateTime={item.created_at}>{formatTimestamp(item.created_at)}</time>
                {item.selected_column && ` · Kolom ${item.selected_column}`} · <CountsSummary counts={item} />
                {item.sha256 && (
                  <div>
                    SHA-256 <code>{item.sha256}</code>{' '}
                    <button type="button" onClick={() => download(item.id, item.source_format)}>Unduh bukti</button>
                    <button type="button" onClick={() => readBatch(item.id)}>Periksa batch</button>
                    {canImport && item.valid_count > 0 && !submittedJobs[item.id] &&
                      <button type="button" onClick={() => queue(item.id)}>Antrekan sumber sintetis</button>}
                    {submittedJobs[item.id] && <p role="status">Pekerjaan <code>{submittedJobs[item.id]}</code> dapat dilihat pada aktivitas kasus.</p>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {details && <section aria-label="Rincian batch impor">
          <h4>Baris impor <code>{details.id}</code></h4>
          <ul>{details.rows.map((row) => <li key={row.row_number}>
            {row.row_number} · {row.reference_label ?? 'Label kosong atau tidak valid'} · {row.status}{row.duplicate && ' · Duplikat'}
          </li>)}</ul>
          <h4>Audit batch terbaru</h4>
          <ul>{details.events.map((event, index) => <li key={index}>
            {event.action} · <time dateTime={event.occurred_at}>{formatTimestamp(event.occurred_at)}</time>
            {event.correlation_id && <> · <code>{event.correlation_id}</code></>}
          </li>)}</ul>
        </section>}
        {history?.next_cursor && <button type="button" onClick={more}>Muat impor sebelumnya</button>}
      </fieldset>
    </section>
  );
}
