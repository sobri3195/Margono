import { isUuid } from './api';
import { isTimestamp } from './contracts';
import { formatTimestamp } from './display';
import { isObject } from './operatorApi';

export type AuditEvent = {
  id: string; action: string; occurred_at: string;
  correlation_id: string | null; actor_id: string | null;
};

export function isAuditEvent(value: unknown): value is AuditEvent {
  return isObject(value) && isUuid(value.id) && typeof value.action === 'string' && isTimestamp(value.occurred_at)
    && (value.correlation_id === null || isUuid(value.correlation_id))
    && (value.actor_id === null || isUuid(value.actor_id));
}

export function AuditEvents({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) return <p>Belum ada peristiwa audit.</p>;
  return <ul>{events.map((event) => <li key={event.id}>
    {event.action} · <time dateTime={event.occurred_at}>{formatTimestamp(event.occurred_at)}</time>
    {' · '}Aktor {event.actor_id ? <code>{event.actor_id}</code> : 'Sistem'}
    {event.correlation_id && <> · ID korelasi <code>{event.correlation_id}</code></>}
  </li>)}</ul>;
}
