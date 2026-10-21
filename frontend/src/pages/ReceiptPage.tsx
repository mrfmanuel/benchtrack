import { Link, useParams } from 'react-router';

import { api } from '../api/client';
import { ErrorBanner, Loading } from '../components/ui';
import { SHOP_NAME } from '../config';
import { useApi } from '../hooks/useApi';
import { formatDate, formatDevice } from '../lib/format';
import { trackingUrl } from '../lib/trackingCode';

/**
 * Printable receipt (spec 9.24): shop name, date, customer name, device, reported issue,
 * tracking code and tracking URL. Nothing else — no phone, cost or internal notes.
 */
export function ReceiptPage() {
  const ticketId = Number(useParams().id);
  const { data: ticket, error } = useApi(() => api.getTicket(ticketId), `receipt-${ticketId}`);

  return (
    <div className="receipt-page">
      <div className="receipt-toolbar no-print">
        <Link to={`/tickets/${ticketId}`} className="button button--secondary">
          Back to ticket
        </Link>
        <button type="button" className="button" onClick={() => window.print()} disabled={!ticket}>
          Print
        </button>
      </div>
      <ErrorBanner error={error} title="Could not load the ticket" />
      {!ticket && !error && <Loading />}
      {ticket && (
        <article className="receipt" aria-label="Repair receipt">
          <header className="receipt__header">
            <h1>{SHOP_NAME}</h1>
            <p>Repair receipt</p>
          </header>
          <dl className="receipt__fields">
            <dt>Date</dt>
            <dd>{formatDate(ticket.created_at)}</dd>
            <dt>Customer</dt>
            <dd>{ticket.customer.name}</dd>
            <dt>Device</dt>
            <dd>{formatDevice(ticket)}</dd>
            <dt>Reported issue</dt>
            <dd className="prewrap">{ticket.reported_issue}</dd>
          </dl>
          <div className="receipt__code">
            <p>Tracking code</p>
            <p className="receipt__code-value">{ticket.tracking_code}</p>
          </div>
          <p className="receipt__url">
            Check your repair status at
            <br />
            <strong>{trackingUrl(ticket.tracking_code)}</strong>
          </p>
          <footer className="receipt__footer">Keep this receipt. You will need the code to pick up your device.</footer>
        </article>
      )}
    </div>
  );
}
