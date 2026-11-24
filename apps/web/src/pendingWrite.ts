import { isUuid } from './api';
import { isObject, RequestError } from './operatorApi';

export type PendingWrite = { key: string; fingerprint: string };

export function readPendingWrite(storageKey: string): PendingWrite | undefined {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null');
    if (isObject(value) && isUuid(value.key)
        && typeof value.fingerprint === 'string' && /^[0-9a-f]{64}$/.test(value.fingerprint)) {
      return { key: value.key, fingerprint: value.fingerprint };
    }
  } catch {
    return undefined;
  }
}

export function savePendingWrite(storageKey: string, operation: PendingWrite) {
  sessionStorage.setItem(storageKey, JSON.stringify(operation));
}

export function clearPendingWrite(storageKey: string, operation: PendingWrite) {
  if (readPendingWrite(storageKey)?.key !== operation.key) return false;
  sessionStorage.removeItem(storageKey);
  return true;
}

export function isWriteRejection(error: unknown) {
  return error instanceof RequestError && [403, 404, 409, 422].includes(error.status);
}

export async function writeFingerprint(body: string) {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body)));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
}
