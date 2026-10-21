import { Link } from 'react-router';

import type { Ticket } from '../api/types';
import { daysSince, formatDateTime, formatDevice } from '../lib/format';
import { StatusBadge } from './ui';

interface Props {
  tickets: Ticket[];
  /** Show "idle for N days" instead of the last update time. */
  showIdle?: boolean;
  /** Hide the customer column (e.g. on the customer page). */
  hideCustomer?: boolean;
  caption: string;
}

/** Ticket list as a table on desktop, stacked cards on small screens (CSS). */
export function TicketTable({ tickets, showIdle, hideCustomer, caption }: Props) {
  return (
    <div className="table-wrap">
      <table className="table table--responsive">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Code</th>
            {!hideCustomer && <th scope="col">Customer</th>}
            <th scope="col">Device</th>
            <th scope="col">Status</th>
            <th scope="col">{showIdle ? 'Idle' : 'Updated'}</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.id}>
              <td data-label="Code">
                <Link to={`/tickets/${ticket.id}`} className="code">
                  {ticket.tracking_code}
                </Link>
              </td>
              {!hideCustomer && <td data-label="Customer">{ticket.customer.name}</td>}
              <td data-label="Device">{formatDevice(ticket)}</td>
              <td data-label="Status">
                <StatusBadge status={ticket.status} />
              </td>
              <td data-label={showIdle ? 'Idle' : 'Updated'}>
                {showIdle ? (
                  `${daysSince(ticket.updated_at)} days`
                ) : (
                  <time dateTime={ticket.updated_at}>{formatDateTime(ticket.updated_at)}</time>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
