import { Component, StrictMode, useEffect, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { CaseConsole } from './CaseConsole';
import { useResource } from './api';
import { decodeCatalog, decodeReadiness, type Catalog, type SyntheticCase, type Workspace } from './contracts';
import { formatTimestamp, rememberSelection, selectionUrl, useTheme } from './display';
import './styles.css';

function CaseDetails({ item, catalog, correlationId }: {
  item: SyntheticCase; catalog: Catalog; correlationId: string | null;
}) {
  const source = catalog.sources.find((profile) => profile.profile_id === item.reference_id);
  const device = catalog.devices.find((profile) => profile.profile_id === item.reference_id);

  return (
    <article className="case-details" aria-labelledby="case-label">
      <p className="case-id">{item.case_id}</p>
      <h2 id="case-label">{item.label}</h2>
      <dl>
        <div><dt>Skenario</dt><dd>{item.scenario}</dd></div>
        <div><dt>Waktu fixture</dt><dd><time dateTime={item.created_at}>{formatTimestamp(item.created_at)}</time></dd></div>
        {source && (
          <>
            <div><dt>Sumber tiruan</dt><dd>{source.label}</dd></div>
            <div>
              <dt>Perilaku sumber</dt>
              <dd>{source.behavior === 'timeout_fixture' ? 'Timeout simulasi' : 'Contoh tersedia'}</dd>
            </div>
          </>
        )}
        {device && (
          <>
            <div><dt>Profil perangkat</dt><dd>{device.platform}</dd></div>
            <div><dt>Kapabilitas</dt><dd>{device.capability}</dd></div>
            <div>
              <dt>Hasil simulasi</dt>
              <dd>{device.result === 'unsupported' ? 'Tidak didukung' : 'Contoh tersedia'}</dd>
            </div>
          </>
        )}
      </dl>
      <p><a href={selectionUrl('case', item.case_id).href}>Tautan kasus sintetis</a></p>
      {correlationId && <p>ID korelasi katalog <code>{correlationId}</code></p>}
    </article>
  );
}

function CatalogView({ catalog, correlationId }: { catalog: Catalog; correlationId: string | null }) {
  function linkedCase() {
    const id = new URLSearchParams(window.location.search).get('case');
    return catalog.cases.find((item) => item.case_id === id);
  }

  const [workspace, setWorkspace] = useState<Workspace>(() => linkedCase()?.workspace ?? 'web');
  const [selection, setSelection] = useState<Partial<Record<Workspace, string>>>(() => {
    const item = linkedCase();
    return item ? { [item.workspace]: item.case_id } : {};
  });
  const cases = catalog.cases.filter((item) => item.workspace === workspace);
  const selected = cases.find((item) => item.case_id === selection[workspace]) ?? cases[0];

  useEffect(() => {
    function handlePop() {
      const id = new URLSearchParams(window.location.search).get('case');
      const item = catalog.cases.find((entry) => entry.case_id === id);
      setWorkspace(item?.workspace ?? 'web');
      setSelection((previous) => ({ ...previous, [item?.workspace ?? 'web']: item?.case_id }));
    }
    window.addEventListener('popstate', handlePop);
    return () => window.removeEventListener('popstate', handlePop);
  }, [catalog]);

  function selectWorkspace(value: Workspace) {
    if (value === workspace) return;
    setWorkspace(value);
    const next = selection[value] ?? catalog.cases.find((item) => item.workspace === value)?.case_id;
    rememberSelection('case', next);
  }

  function selectCase(id: string) {
    setSelection((previous) => ({ ...previous, [workspace]: id }));
    rememberSelection('case', id);
  }

  return (
    <section className="workspace" aria-label="Katalog kasus">
      <div className="workspace-list" role="group" aria-label="Workspace">
        <button type="button" aria-pressed={workspace === 'web'} onClick={() => selectWorkspace('web')}>
          Web Intelligence
        </button>
        <button type="button" aria-pressed={workspace === 'usb'} onClick={() => selectWorkspace('usb')}>
          USB Security
        </button>
      </div>
      {selected ? (
        <div className="workspace-content">
          <div className="case-picker">
            <label htmlFor="case-id">Kasus sintetis</label>
            <select id="case-id" value={selected.case_id} onChange={(event) => selectCase(event.target.value)}>
              {cases.map((item) => (
                <option key={item.case_id} value={item.case_id}>{item.case_id} · {item.label}</option>
              ))}
            </select>
          </div>
          <CaseDetails item={selected} catalog={catalog} correlationId={correlationId} />
        </div>
      ) : <p className="message">Belum ada kasus untuk workspace ini.</p>}
    </section>
  );
}

function CatalogError({ message, correlationId, retry }: {
  message: string;
  correlationId: string | null;
  retry: () => void;
}) {
  return (
    <div className="message">
      <p role="alert">{message}</p>
      {correlationId && <p>ID korelasi <code>{correlationId}</code></p>}
      <button type="button" onClick={retry}>Coba lagi</button>
    </div>
  );
}

class CatalogBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

const databaseLabels = {
  ready: 'Siap',
  not_configured: 'Belum dikonfigurasi',
  unavailable: 'Tidak dapat dihubungi',
  migration_required: 'Memerlukan migrasi',
};

const workerLabels = {
  active: 'Aktif',
  not_observed: 'Belum terdeteksi',
  unavailable: 'Tidak dapat diperiksa',
};

function SystemStatus() {
  const { state, retry } = useResource('/api/v1/readiness', decodeReadiness, 503);

  return (
    <section className="message system-status" aria-labelledby="system-status-label">
      <h2 id="system-status-label">Status operasional</h2>
      {state.status === 'loading' && <p role="status">Memeriksa kesiapan…</p>}
      {state.status === 'error' && (
        <>
          <p role="status">Status kesiapan tidak dapat dimuat.</p>
          {state.correlationId && <p>ID korelasi <code>{state.correlationId}</code></p>}
          <button type="button" onClick={retry}>Periksa status lagi</button>
        </>
      )}
      {state.status === 'ready' && (
        <>
          <dl>
            <div><dt>PostgreSQL</dt><dd>{databaseLabels[state.data.checks.database]}</dd></div>
            <div><dt>Worker</dt><dd>{workerLabels[state.data.checks.worker]}</dd></div>
            <div><dt>Sinkronisasi</dt><dd>Belum tersedia</dd></div>
            <div><dt>Pilot</dt><dd>Belum siap</dd></div>
          </dl>
          {state.data.checks.database === 'unavailable' && state.correlationId && (
            <p>ID korelasi <code>{state.correlationId}</code></p>
          )}
          <button type="button" onClick={retry}>Periksa status lagi</button>
        </>
      )}
    </section>
  );
}

const catalogFailureMessages = {
  request: 'Katalog tidak dapat dimuat. Periksa layanan API lokal.',
  invalid: 'Respons katalog tidak valid.',
  timeout: 'Permintaan katalog melewati batas waktu.',
};

function App() {
  const { theme, setTheme } = useTheme();
  const { state, retry, attempt } = useResource('/api/v1/simulation/catalog', decodeCatalog);

  return (
    <main className="page">
      <header>
        <p className="brand">MARGONO</p>
        <h1>Katalog simulasi</h1>
        <p className="intro">Kasus dan profil sintetis untuk pengembangan lokal.</p>
        <div className="theme-control">
          <label htmlFor="theme">Tema</label>
          <select id="theme" value={theme} onChange={(event) => {
            const value = event.target.value;
            if (value === 'system' || value === 'light' || value === 'dark') setTheme(value);
          }}>
            <option value="system">Ikuti sistem</option>
            <option value="light">Terang</option>
            <option value="dark">Gelap</option>
          </select>
        </div>
      </header>
      {state.status === 'loading' && <p role="status" className="message">Memuat katalog…</p>}
      {state.status === 'error' && (
        <CatalogError message={catalogFailureMessages[state.reason]} correlationId={state.correlationId} retry={retry} />
      )}
      {state.status === 'ready' && (
        <CatalogBoundary key={attempt} fallback={
          <CatalogError message="Katalog tidak dapat ditampilkan." correlationId={state.correlationId} retry={retry} />
        }>
          <CatalogView catalog={state.data} correlationId={state.correlationId} />
        </CatalogBoundary>
      )}
      <SystemStatus />
      {state.status === 'ready' && <CaseConsole fixtures={state.data.cases} />}
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
