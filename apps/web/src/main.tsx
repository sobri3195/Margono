import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Workspace = 'web' | 'usb';

type Catalog = {
  mode: 'SYNTHETIC';
  cases: SyntheticCase[];
  sources: SourceProfile[];
  devices: DeviceProfile[];
};

type SyntheticCase = {
  case_id: string;
  label: string;
  workspace: Workspace;
  scenario: string;
  reference_id: string;
};

type SourceProfile = {
  profile_id: string;
  label: string;
  behavior: 'fixture_available' | 'timeout_fixture';
};

type DeviceProfile = {
  profile_id: string;
  platform: 'Android' | 'iPhone';
  capability: string;
  result: 'sample_available' | 'unsupported';
};

type CatalogState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; catalog: Catalog };

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

function App() {
  const [state, setState] = useState<CatalogState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    async function loadCatalog() {
      try {
        const response = await fetch('/api/v1/simulation/catalog', { signal: controller.signal });
        if (!response.ok) throw new Error(`Catalog status: ${response.status}`);
        const catalog: Catalog = await response.json();
        if (catalog.mode !== 'SYNTHETIC') throw new Error('Expected a synthetic catalog');
        if (!controller.signal.aborted) setState({ status: 'ready', catalog });
      } catch {
        if (!controller.signal.aborted) setState({ status: 'error' });
      }
    }

    void loadCatalog();
    return () => controller.abort();
  }, [attempt]);

  function retry() {
    setState({ status: 'loading' });
    setAttempt((value) => value + 1);
  }

  return (
    <main className="page">
      <header>
        <p className="brand">MARGONO</p>
        <h1>Katalog simulasi</h1>
        <p className="intro">Kasus dan profil sintetis untuk pengembangan lokal.</p>
      </header>
      {state.status === 'loading' && <p role="status" className="message">Memuat katalog…</p>}
      {state.status === 'error' && (
        <div className="message">
          <p role="alert">Katalog tidak dapat dimuat. Periksa layanan API lokal.</p>
          <button type="button" onClick={retry}>Coba lagi</button>
        </div>
      )}
      {state.status === 'ready' && <CatalogView catalog={state.catalog} />}
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
