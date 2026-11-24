import { readCorrelationId } from './api';

export type Session = { token: string; userId: string; roles: string[] };

export class RequestError extends Error {
  constructor(readonly status: number, readonly correlationId: string | null) {
    super('Operator request failed');
  }
}

export async function operatorResponse(path: string, options: RequestInit = {}, session?: Session) {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (session) headers.set('Authorization', `Bearer ${session.token}`);
  const timeout = AbortSignal.timeout(10_000);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  const response = await fetch(`/api/v1${path}`, { ...options, headers, cache: 'no-store', signal });
  if (!response.ok) throw new RequestError(response.status, readCorrelationId(response));
  return response;
}

export async function request(path: string, options?: RequestInit, session?: Session): Promise<unknown> {
  const response = await operatorResponse(path, options, session);
  return response.status === 204 ? null : response.json();
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
