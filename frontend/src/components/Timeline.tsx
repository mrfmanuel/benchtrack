import type { PublicTimelineEntry, TicketEvent, TicketStatus } from '../api/types';
import { formatDateTime } from '../lib/format';
import { PROGRESS_STEPS, STATUS_TONES, progressIndex, statusLabel } from '../lib/statuses';

/** Staff timeline: status changes and notes, oldest first. */
export function Timeline({ events }: { events: TicketEvent[] }) {
  if (events.length === 0) return <p className="muted">No events yet.</p>;
  return (
    <ol className="timeline">
      {events.map((event) => (
        <li
          key={event.id}
          className={`timeline__item timeline__item--${event.kind === 'status' && event.to_status ? STATUS_TONES[event.to_status] : 'note'}`}
        >
          <div className="timeline__head">
            {event.kind === 'status' && event.to_status ? (
              <strong>
                {event.from_status
                  ? `${statusLabel(event.from_status)} → ${statusLabel(event.to_status)}`
                  : `Ticket created: ${statusLabel(event.to_status)}`}
              </strong>
            ) : (
              <strong>Note</strong>
            )}
            <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
          </div>
          {event.note && <p className="timeline__note">{event.note}</p>}
        </li>
      ))}
    </ol>
  );
}

/** Public timeline: status and time only. */
export function PublicTimeline({ timeline }: { timeline: PublicTimelineEntry[] }) {
  return (
    <ol className="timeline" aria-label="Status history">
      {timeline.map((entry, index) => (
        <li key={`${entry.at}-${index}`} className={`timeline__item timeline__item--${STATUS_TONES[entry.status]}`}>
          <div className="timeline__head">
            <strong>{statusLabel(entry.status)}</strong>
            <time dateTime={entry.at}>{formatDateTime(entry.at)}</time>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Steps of the happy path; cancelled tickets get a single notice instead. */
export function ProgressIndicator({ status }: { status: TicketStatus }) {
  const current = progressIndex(status);
  if (current === -1) {
    return <p className="progress-cancelled">This repair was cancelled.</p>;
  }
  return (
    <ol className="progress" aria-label={`Progress: step ${current + 1} of ${PROGRESS_STEPS.length}`}>
      {PROGRESS_STEPS.map((step, index) => {
        const state = index < current ? 'done' : index === current ? 'current' : 'todo';
        return (
          <li
            key={step}
            className={`progress__step progress__step--${state}`}
            aria-current={state === 'current' ? 'step' : undefined}
          >
            <span className="progress__dot" aria-hidden="true" />
            <span className="progress__label">{statusLabel(step)}</span>
          </li>
        );
      })}
    </ol>
  );
}
