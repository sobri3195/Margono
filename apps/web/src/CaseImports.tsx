import { useEffect, useLayoutEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { isUuid } from './api';
import { isTimestamp } from './contracts';
import { formatTimestamp } from './display';
import { isObject, operatorResponse, request, RequestError, type Session } from './operatorApi';

type Counts = { row_count: number; valid_count: number; invalid_count: number };
type Result = Counts & { id: string; sha256: string };
type Summary = Counts & { id: string; created_at: string; selected_column: string | null; sha256: string | null };
type History = { items: Summary[]; next_cursor: string | null };
type PreviewRow = {
  row_number: number;
  reference_label: string | null;
  status: 'valid' | 'invalid';
  duplicate: boolean;
};
type Inspection = {
  caseId: string;
  payload: { content: string; column: string };
  rows: PreviewRow[];
  key: string;
};
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
    && (value.sha256 === null || typeof value.sha256 === 'string') && isCounts(value);
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

function importIssue(error: unknown, fallback: string): Issue {
  if (!(error instanceof RequestError)) return { message: fallback };
  const message = error.status === 422 ? 'Periksa format CSV atau pilihan kolom.'
    : error.status === 409 ? 'Impor tidak dapat diproses untuk status kasus atau kunci ini.' : fallback;
  return { message, correlationId: error.correlationId };
}

function CountsSummary({ counts }: { counts: Counts }) {
  const pending = counts.row_count - counts.valid_count - counts.invalid_count;
  return <>{counts.valid_count} valid, {counts.invalid_count} tidak valid{pending > 0 && `, ${pending} menunggu`}</>;
}

export function CaseImports({ caseId, session, canImport, onSessionExpired }: {
  caseId: string;
  session: Session;
  canImport: boolean;
  onSessionExpired: (correlationId: string | null) => void;
}) {
  const path = `/cases/${caseId}/imports`;
  const lifetime = useRef<AbortController>(null);
  const [file, setFile] = useState<{ content: string; columns: string[] }>();
  const [column, setColumn] = useState('');
  const [inspection, setInspection] = useState<Inspection>();
  const [result, setResult] = useState<Counts>();
  const [issue, setIssue] = useState<Issue>();
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<History>();
  const [historyIssue, setHistoryIssue] = useState<Issue>();
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const visibleInspection = inspection?.caseId === caseId ? inspection : undefined;

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

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    setFile(undefined);
    setColumn('');
    setInspection(undefined);
    setResult(undefined);
    setIssue(undefined);
    if (!selected) return;
    if (!selected.size || selected.size > 65_536) {
      setIssue({ message: 'Pilih CSV UTF-8 dengan ukuran hingga 64 KiB.' });
      return;
    }
    void perform(async (signal) => {
      const content = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await selected.arrayBuffer());
      signal.throwIfAborted();
      const data = await request(`${path}/columns`, {
        method: 'POST', body: JSON.stringify({ content }), signal,
      }, session);
      signal.throwIfAborted();
      if (!isObject(data) || !Array.isArray(data.columns) || !data.columns.every((value) => typeof value === 'string')) {
        throw new Error('Unexpected column response');
      }
      const columns = data.columns.filter((name: string) => name.length <= 128);
      if (!columns.length) throw new Error('No selectable column');
      setFile({ content, columns });
      setColumn(columns.includes('Nama') ? 'Nama' : columns[0]);
    }, 'Kolom gagal dibaca. Pilih CSV UTF-8 dengan header yang valid.');
  }

  function preview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !column) return;
    setInspection(undefined);
    setResult(undefined);
    const payload = { content: file.content, column };
    void perform(async (signal) => {
      const data = await request(`${path}/preview`, { method: 'POST', body: JSON.stringify(payload), signal }, session);
      signal.throwIfAborted();
      if (!isObject(data) || !Array.isArray(data.rows) || !data.rows.every(isPreviewRow)) {
        throw new Error('Unexpected preview response');
      }
      setInspection({ caseId, payload, rows: data.rows, key: crypto.randomUUID() });
    }, 'Pratinjau CSV gagal dimuat.');
  }

  function confirm() {
    if (!canImport || !visibleInspection) return;
    const pending = visibleInspection;
    void perform(async (signal) => {
      const data = await request(`/cases/${pending.caseId}/imports`, {
        method: 'POST', headers: { 'Idempotency-Key': pending.key },
        body: JSON.stringify(pending.payload), signal,
      }, session);
      signal.throwIfAborted();
      if (!isResult(data)) throw new Error('Unexpected import result');
      setResult(data);
      setInspection(undefined);
      setHistoryAttempt((previous) => previous + 1);
    }, 'Konfirmasi impor gagal. Coba lagi untuk memakai kunci impor yang sama.');
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

  function download(id: string) {
    void perform(async (signal) => {
      const response = await operatorResponse(`${path}/${id}/evidence`, { signal }, session);
      const data = await response.blob();
      signal.throwIfAborted();
      const url = URL.createObjectURL(data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `bukti-${id}.csv.bin`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, 'Bukti impor gagal diunduh.');
  }

  return (
    <section aria-label="Impor CSV">
      <fieldset disabled={busy}>
        {issue && <p role="alert">{issue.message} {issue.correlationId && <code>{issue.correlationId}</code>}</p>}
        {canImport && (
          <form onSubmit={preview}>
            <label>CSV sintetis <input type="file" accept=".csv,text/csv" onChange={chooseFile} /></label>
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
            <button type="submit" disabled={!file}>Pratinjau CSV</button>
          </form>
        )}
        {canImport && visibleInspection && (
          <>
            <ul aria-label="Pratinjau baris CSV">
              {visibleInspection.rows.map((row) => (
                <li key={row.row_number}>
                  {row.row_number} · {row.reference_label ?? 'Label kosong atau tidak valid'} · {row.status === 'valid' ? 'valid' : 'tidak valid'}
                  {row.duplicate && ' · Duplikat'}
                </li>
              ))}
            </ul>
            <button type="button" onClick={confirm}>Konfirmasi impor</button>
          </>
        )}
        {result && <p role="status">{result.row_count} baris tersimpan. <CountsSummary counts={result} />.</p>}
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
                    <button type="button" onClick={() => download(item.id)}>Unduh bukti</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {history?.next_cursor && <button type="button" onClick={more}>Muat impor sebelumnya</button>}
      </fieldset>
    </section>
  );
}
