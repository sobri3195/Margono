import { Component, StrictMode, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { useResource } from './api';
import { decodeCatalog, decodeReadiness, type Catalog, type SyntheticCase, type Workspace } from './contracts';
import './styles.css';

function CaseDetails({ item, catalog }: { item: SyntheticCase; catalog: Catalog }) {
  const source = catalog.sources.find((profile) => profile.profile_id === item.reference_id);
  const device = catalog.devices.find((profile) => profile.profile_id === item.reference_id);

  return (
    <article className="case-details" aria-labelledby="case-label">
      <p className="case-id">{item.case_id}</p>
      <h2 id="case-label">{item.label}</h2>
      <dl>
        <div><dt>Skenario</dt><dd>{item.scenario}</dd></div>
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
    </article>
  );
}

function CatalogView({ catalog }: { catalog: Catalog }) {
  const [workspace, setWorkspace] = useState<Workspace>('web');
  const [selectedId, setSelectedId] = useState('');
  const cases = catalog.cases.filter((item) => item.workspace === workspace);
  const selected = cases.find((item) => item.case_id === selectedId) ?? cases[0];

  function selectWorkspace(value: Workspace) {
    setWorkspace(value);
    setSelectedId('');
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
            <select id="case-id" value={selected.case_id} onChange={(event) => setSelectedId(event.target.value)}>
              {cases.map((item) => (
                <option key={item.case_id} value={item.case_id}>{item.case_id} · {item.label}</option>
              ))}
            </select>
          </div>
          <CaseDetails item={selected} catalog={catalog} />
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
            <div><dt>Worker</dt><dd>Belum tersedia</dd></div>
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
  const { state, retry, attempt } = useResource('/api/v1/simulation/catalog', decodeCatalog);

  return (
    <main className="page">
      <header>
        <p className="brand">MARGONO</p>
        <h1>Katalog simulasi</h1>
        <p className="intro">Kasus dan profil sintetis untuk pengembangan lokal.</p>
      </header>
      {state.status === 'loading' && <p role="status" className="message">Memuat katalog…</p>}
      {state.status === 'error' && (
        <CatalogError message={catalogFailureMessages[state.reason]} correlationId={state.correlationId} retry={retry} />
      )}
      {state.status === 'ready' && (
        <CatalogBoundary key={attempt} fallback={
          <CatalogError message="Katalog tidak dapat ditampilkan." correlationId={state.correlationId} retry={retry} />
        }>
          <CatalogView catalog={state.data} />
        </CatalogBoundary>
      )}
      <SystemStatus />
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
