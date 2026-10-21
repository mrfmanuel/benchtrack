import { useState, type FormEvent } from 'react';

import { api, type ApiError } from '../api/client';
import type { Ticket, TicketStatus } from '../api/types';
import { toApiError } from '../hooks/useApi';
import { allowedNextStatuses, isFinal, statusLabel } from '../lib/statuses';
import { TextAreaField, SelectField } from './fields';
import { ErrorBanner } from './ui';

interface Props {
  ticket: Ticket;
  onChanged: (ticket: Ticket) => void;
}

/** Offers only the statuses the workflow allows next; nothing for final tickets. */
export function StatusChangeControl({ ticket, onChanged }: Props) {
  const options = allowedNextStatuses(ticket.status);
  const [toStatus, setToStatus] = useState<TicketStatus | ''>('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);

  if (isFinal(ticket.status)) {
    return (
      <p className="muted" data-testid="status-final">
        This ticket is {statusLabel(ticket.status).toLowerCase()}. Its status can no longer change.
      </p>
    );
  }

  const fieldError = error?.fieldErrors.find((e) => e.field === 'note')?.message;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!toStatus) return;
    setSaving(true);
    setError(null);
    try {
      const trimmed = note.trim();
      const updated = await api.changeTicketStatus(ticket.id, {
        to_status: toStatus,
        ...(trimmed ? { note: trimmed } : {}),
      });
      setToStatus('');
      setNote('');
      onChanged(updated);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit} noValidate aria-label="Change status">
      <ErrorBanner error={error && error.code !== 'validation_error' ? error : null} title="Status not changed" />
      <SelectField
        id="to_status"
        label="New status"
        required
        value={toStatus}
        onChange={(e) => setToStatus(e.target.value as TicketStatus | '')}
      >
        <option value="" disabled>
          Choose the next status…
        </option>
        {options.map((status) => (
          <option key={status} value={status}>
            {statusLabel(status)}
          </option>
        ))}
      </SelectField>
      <TextAreaField
        id="status_note"
        label="Note for the timeline"
        maxLength={1000}
        rows={2}
        value={note}
        error={fieldError}
        onChange={(e) => setNote(e.target.value)}
      />
      <div>
        <button type="submit" className="button" disabled={!toStatus || saving}>
          {saving ? 'Saving…' : 'Change status'}
        </button>
      </div>
    </form>
  );
}
