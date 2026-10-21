import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router';

import { api, type ApiError } from '../api/client';
import type { Ticket } from '../api/types';
import { StatusChangeControl } from '../components/StatusChangeControl';
import { TicketFields } from '../components/TicketFields';
import { Timeline } from '../components/Timeline';
import { TextAreaField } from '../components/fields';
import { Banner, ErrorBanner, Loading, PageHeader, StatusBadge } from '../components/ui';
import { toApiError, useApi } from '../hooks/useApi';
import { DEVICE_TYPE_LABELS, formatDateTime, formatMoney } from '../lib/format';
import { changedFields, splitFieldErrors, type FieldErrors } from '../lib/forms';
import { isFinal, statusLabel } from '../lib/statuses';
import { TICKET_FORM_FIELDS, formValuesToPayload, ticketToFormValues, type TicketFormValues } from '../lib/ticketForm';
import { NotFoundPage } from './NotFoundPage';

export function TicketDetailPage() {
  const ticketId = Number(useParams().id);
  const ticketState = useApi(() => api.getTicket(ticketId), `ticket-${ticketId}`);
  const events = useApi(() => api.listTicketEvents(ticketId), `events-${ticketId}`);
  const ticket = ticketState.data;

  if (!Number.isInteger(ticketId) || ticketId < 1 || ticketState.error?.status === 404) {
    return <NotFoundPage what="Ticket" />;
  }
  if (ticketState.error) return <ErrorBanner error={ticketState.error} title="Could not load the ticket" />;
  if (!ticket) return <Loading />;

  function refresh(updated: Ticket) {
    ticketState.setData(updated);
    events.reload();
  }

  const final = isFinal(ticket.status);

  return (
    <>
      <PageHeader
        title={
          <>
            <span className="code">{ticket.tracking_code}</span> <StatusBadge status={ticket.status} />
          </>
        }
        actions={
          <Link to={`/tickets/${ticket.id}/receipt`} className="button button--secondary">
            Print receipt
          </Link>
        }
      >
        <p className="muted">
          Customer: <Link to={`/customers/${ticket.customer.id}`}>{ticket.customer.name}</Link> · {ticket.customer.phone}
          <br />
          Created {formatDateTime(ticket.created_at)} · Updated {formatDateTime(ticket.updated_at)}
        </p>
      </PageHeader>

      {final && (
        <Banner tone="info" title={`This ticket is ${statusLabel(ticket.status).toLowerCase()}`}>
          Details and status are read-only. Notes can still be added.
        </Banner>
      )}

      <div className="detail-grid">
        <section className="card" aria-labelledby="details-title">
          <TicketDetails key={ticket.updated_at} ticket={ticket} onSaved={refresh} />
        </section>

        <div className="stack">
          <section className="card" aria-labelledby="status-title">
            <h2 id="status-title">Status</h2>
            <StatusChangeControl ticket={ticket} onChanged={refresh} />
          </section>
          <section className="card" aria-labelledby="note-title">
            <h2 id="note-title">Add a note</h2>
            <NoteForm ticketId={ticket.id} onAdded={() => {
              events.reload();
              ticketState.reload();
            }} />
          </section>
        </div>
      </div>

      <section className="card section" aria-labelledby="timeline-title">
        <h2 id="timeline-title">Timeline</h2>
        <ErrorBanner error={events.error} title="Could not load the timeline" />
        {events.loading && !events.data && <Loading />}
        {events.data && <Timeline events={events.data.items} />}
      </section>
    </>
  );
}

function TicketDetails({ ticket, onSaved }: { ticket: Ticket; onSaved: (t: Ticket) => void }) {
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<TicketFormValues>(() => ticketToFormValues(ticket));
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const final = isFinal(ticket.status);

  function cancel() {
    setValues(ticketToFormValues(ticket));
    setFieldErrors({});
    setError(null);
    setEditing(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const result = formValuesToPayload(values);
    if ('errors' in result) {
      setFieldErrors(result.errors);
      return;
    }
    const changes = changedFields(ticket, result.payload);
    if (Object.keys(changes).length === 0) {
      setFieldErrors({});
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateTicket(ticket.id, changes);
      setEditing(false);
      onSaved(updated);
    } catch (err) {
      const apiError = toApiError(err);
      const { fields, other } = splitFieldErrors(apiError.fieldErrors, TICKET_FORM_FIELDS);
      setFieldErrors(fields);
      setError(apiError);
      if (other.length) setNotice(other.join(' '));
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <>
        <div className="card__header">
          <h2 id="details-title">Details</h2>
          {!final && (
            <button type="button" className="button button--secondary" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
        <dl className="details">
          <dt>Device</dt>
          <dd>{DEVICE_TYPE_LABELS[ticket.device_type]}</dd>
          <dt>Brand / model</dt>
          <dd>{[ticket.brand, ticket.model].filter(Boolean).join(' ')}</dd>
          <dt>Serial number</dt>
          <dd>{ticket.serial_number ?? '—'}</dd>
          <dt>Reported issue</dt>
          <dd className="prewrap">{ticket.reported_issue}</dd>
          <dt>Diagnosis</dt>
          <dd className="prewrap">{ticket.diagnosis ?? '—'}</dd>
          <dt>Estimated cost</dt>
          <dd>{formatMoney(ticket.estimated_cost)}</dd>
        </dl>
      </>
    );
  }

  return (
    <form className="stack" onSubmit={submit} noValidate aria-labelledby="details-title">
      <h2 id="details-title">Edit details</h2>
      <ErrorBanner error={error} title="Changes not saved">
        {notice && <p>{notice}</p>}
      </ErrorBanner>
      <TicketFields values={values} errors={fieldErrors} onChange={setValues} />
      <div className="actions">
        <button type="submit" className="button" disabled={saving}>
          {saving ? 'Saving…' : 'Save changes'}
        </button>
        <button type="button" className="button button--secondary" onClick={cancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function NoteForm({ ticketId, onAdded }: { ticketId: number; onAdded: () => void }) {
  const [note, setNote] = useState('');
  const [error, setError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);
  const fieldError = error?.fieldErrors.find((e) => e.field === 'note')?.message;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.addTicketNote(ticketId, { note: note.trim() });
      setNote('');
      onAdded();
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate aria-label="Add a note">
      <ErrorBanner error={error && !fieldError ? error : null} title="Note not added" />
      <TextAreaField
        id="note"
        label="Note"
        required
        maxLength={1000}
        hint="Internal only — never shown on the public tracking page."
        value={note}
        error={fieldError}
        onChange={(e) => setNote(e.target.value)}
      />
      <div>
        <button type="submit" className="button" disabled={saving}>
          {saving ? 'Adding…' : 'Add note'}
        </button>
      </div>
    </form>
  );
}
