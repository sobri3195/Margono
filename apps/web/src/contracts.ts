export type Workspace = 'web' | 'usb';

export type Catalog = {
  mode: 'SYNTHETIC';
  cases: SyntheticCase[];
  sources: SourceProfile[];
  devices: DeviceProfile[];
};

export type SyntheticCase = {
  case_id: string;
  label: string;
  workspace: Workspace;
  scenario: string;
  reference_id: string;
  created_at: string;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function isCase(value: unknown): value is SyntheticCase {
  return isRecord(value) && typeof value.case_id === 'string'
    && typeof value.label === 'string' && (value.workspace === 'web' || value.workspace === 'usb')
    && typeof value.scenario === 'string' && typeof value.reference_id === 'string'
    && isTimestamp(value.created_at);
}

function isSource(value: unknown): value is SourceProfile {
  return isRecord(value) && typeof value.profile_id === 'string' && typeof value.label === 'string'
    && (value.behavior === 'fixture_available' || value.behavior === 'timeout_fixture');
}

function isDevice(value: unknown): value is DeviceProfile {
  return isRecord(value) && typeof value.profile_id === 'string' && typeof value.capability === 'string'
    && (value.platform === 'Android' || value.platform === 'iPhone')
    && (value.result === 'sample_available' || value.result === 'unsupported');
}

function isList<T>(value: unknown, isItem: (item: unknown) => item is T): value is T[] {
  return Array.isArray(value) && value.every(isItem);
}

export function decodeCatalog(value: unknown): Catalog | undefined {
  if (isRecord(value) && value.mode === 'SYNTHETIC' && isList(value.cases, isCase)
      && isList(value.sources, isSource) && isList(value.devices, isDevice)) {
    return { mode: value.mode, cases: value.cases, sources: value.sources, devices: value.devices };
  }
}

type DatabaseStatus = 'ready' | 'not_configured' | 'unavailable' | 'migration_required';
type WorkerStatus = 'active' | 'not_observed' | 'unavailable';
type Readiness = {
  checks: { database: DatabaseStatus; worker: WorkerStatus; sync: 'not_implemented' };
};

export function decodeReadiness(value: unknown): Readiness | undefined {
  if (!isRecord(value) || value.status !== 'not_ready' || value.mode !== 'SYNTHETIC' || value.pilot !== 'blocked'
      || !isRecord(value.checks) || value.checks.sync !== 'not_implemented') return;
  const { database, worker, sync } = value.checks;
  if (worker !== 'active' && worker !== 'not_observed' && worker !== 'unavailable') return;
  if (database === 'ready' || database === 'not_configured' || database === 'unavailable' || database === 'migration_required') {
    return { checks: { database, worker, sync } };
  }
}
