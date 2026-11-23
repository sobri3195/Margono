import { useEffect, useState } from 'react';

const REQUEST_TIMEOUT_MS = 10_000;

type Failure = 'request' | 'invalid' | 'timeout';
type Resource<T> =
  | { status: 'loading' }
  | { status: 'error'; reason: Failure; correlationId: string | null }
  | { status: 'ready'; data: T; correlationId: string | null };

export function useResource<T>(
  path: string,
  decode: (value: unknown) => T | undefined,
  expectedStatus = 200,
) {
  const [state, setState] = useState<Resource<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let correlationId: string | null = null;
    const deadline = window.setTimeout(() => {
      controller.abort();
      setState({ status: 'error', reason: 'timeout', correlationId });
    }, REQUEST_TIMEOUT_MS);

    async function load() {
      let reason: Failure = 'request';
      try {
        const response = await fetch(path, { signal: controller.signal });
        const id = response.headers.get('X-Correlation-ID');
        if (id && /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(id)) {
          correlationId = id;
        }
        if (response.status !== expectedStatus) throw new Error('Unexpected HTTP status');
        reason = 'invalid';
        const data = decode(await response.json());
        if (!data) throw new Error('Invalid response structure');
        if (!controller.signal.aborted) setState({ status: 'ready', data, correlationId });
      } catch {
        if (!controller.signal.aborted) setState({ status: 'error', reason, correlationId });
      } finally {
        window.clearTimeout(deadline);
      }
    }

    void load();
    return () => {
      window.clearTimeout(deadline);
      controller.abort();
    };
  }, [path, decode, expectedStatus, attempt]);

  function retry() {
    setState({ status: 'loading' });
    setAttempt((value) => value + 1);
  }

  return { state, retry, attempt };
}
