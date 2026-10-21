// Readable banner text for API errors (409s, 429s, network failures...).

import { TICKET_STATUSES, type TicketStatus } from '../api/types';
import { statusLabel } from './statuses';

export interface ErrorLike {
  code: string;
  message: string;
  details?: unknown;
  retryAfter?: number | null;
}

function isStatus(value: unknown): value is TicketStatus {
  return typeof value === 'string' && (TICKET_STATUSES as readonly string[]).includes(value);
}

/** `allowed` from an `invalid_transition` error, or `null`. */
export function allowedFromError(error: ErrorLike): TicketStatus[] | null {
  if (error.code !== 'invalid_transition') return null;
  const allowed = (error.details as { allowed?: unknown } | undefined)?.allowed;
  return Array.isArray(allowed) ? allowed.filter(isStatus) : null;
}

/** `existing_customer_id` from a duplicate-phone `conflict`, or `null`. */
export function existingCustomerId(error: ErrorLike): number | null {
  if (error.code !== 'conflict') return null;
  const id = (error.details as { existing_customer_id?: unknown } | undefined)?.existing_customer_id;
  return typeof id === 'number' ? id : null;
}

export function retryMessage(seconds: number | null | undefined): string {
  if (!seconds) return 'Please wait a minute and try again.';
  return `Please wait ${seconds} second${seconds === 1 ? '' : 's'} and try again.`;
}

export function describeError(error: ErrorLike): string {
  switch (error.code) {
    case 'invalid_transition': {
      const allowed = allowedFromError(error);
      if (allowed === null) return error.message;
      const options = allowed.length ? allowed.map(statusLabel).join(', ') : 'none';
      return `${error.message} Allowed next statuses: ${options}.`;
    }
    case 'ticket_final':
      return `${error.message} Notes can still be added.`;
    case 'rate_limited':
      return `Too many requests. ${retryMessage(error.retryAfter)}`;
    case 'validation_error':
      return 'Some fields need attention. Check the highlighted fields.';
    default:
      return error.message;
  }
}
