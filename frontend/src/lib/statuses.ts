// Status workflow (spec F3), mirroring backend/app/services/transitions.py.
// The backend enforces it; the UI uses it to offer only valid next statuses.

import { TICKET_STATUSES, type TicketStatus } from '../api/types';

export const ALLOWED_TRANSITIONS: Readonly<Record<TicketStatus, readonly TicketStatus[]>> = {
  received: ['diagnosing', 'cancelled'],
  diagnosing: ['waiting_parts', 'repairing', 'ready', 'cancelled'],
  waiting_parts: ['repairing', 'cancelled'],
  repairing: ['waiting_parts', 'ready', 'cancelled'],
  ready: ['delivered', 'repairing'],
  delivered: [],
  cancelled: [],
};

export const FINAL_STATUSES: readonly TicketStatus[] = ['delivered', 'cancelled'];

export const OPEN_STATUSES: readonly TicketStatus[] = TICKET_STATUSES.filter(
  (s) => !FINAL_STATUSES.includes(s),
);

/** The happy path shown as a progress indicator (cancelled is off the path). */
export const PROGRESS_STEPS: readonly TicketStatus[] = [
  'received',
  'diagnosing',
  'waiting_parts',
  'repairing',
  'ready',
  'delivered',
];

export function isFinal(status: TicketStatus): boolean {
  return FINAL_STATUSES.includes(status);
}

/** Next statuses in workflow order (same order as TICKET_STATUSES). */
export function allowedNextStatuses(status: TicketStatus): TicketStatus[] {
  const allowed = ALLOWED_TRANSITIONS[status];
  return TICKET_STATUSES.filter((s) => allowed.includes(s));
}

export function isTransitionAllowed(from: TicketStatus, to: TicketStatus): boolean {
  return ALLOWED_TRANSITIONS[from].includes(to);
}

export const STATUS_LABELS: Readonly<Record<TicketStatus, string>> = {
  received: 'Received',
  diagnosing: 'Diagnosing',
  waiting_parts: 'Waiting for parts',
  repairing: 'Repairing',
  ready: 'Ready for pickup',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
};

/** Customer-facing explanation on the public tracking page. */
export const STATUS_DESCRIPTIONS: Readonly<Record<TicketStatus, string>> = {
  received: 'We have received your device and it is in the queue.',
  diagnosing: 'A technician is checking your device to find the problem.',
  waiting_parts: 'We are waiting for a part to arrive.',
  repairing: 'Your device is being repaired.',
  ready: 'Your device is ready. You can pick it up at the shop.',
  delivered: 'Your device has been picked up. Thank you!',
  cancelled: 'This repair was cancelled. Contact the shop if you have questions.',
};

/** Color tone per status; maps to `.badge--<tone>` / `.card--<tone>` in CSS. */
export type StatusTone = 'blue' | 'purple' | 'amber' | 'orange' | 'green' | 'gray' | 'red';

export const STATUS_TONES: Readonly<Record<TicketStatus, StatusTone>> = {
  received: 'blue',
  diagnosing: 'purple',
  waiting_parts: 'amber',
  repairing: 'orange',
  ready: 'green',
  delivered: 'gray',
  cancelled: 'red',
};

export function statusLabel(status: TicketStatus): string {
  return STATUS_LABELS[status];
}

/**
 * Index of the current step in PROGRESS_STEPS, or -1 for cancelled.
 */
export function progressIndex(status: TicketStatus): number {
  return PROGRESS_STEPS.indexOf(status);
}

export type ProgressState = 'done' | 'current' | 'skipped' | 'todo';

/**
 * State of each happy-path step for a ticket, from the statuses it actually went through
 * (`reached`: every `to_status` / public timeline status). A step before the current one is
 * `done` only if the ticket was in it; otherwise it was `skipped` (e.g. diagnosing → repairing
 * skips waiting_parts). Steps after the current one are `todo`, even if reached earlier
 * (ready → repairing puts "ready" ahead again). Empty for cancelled tickets.
 */
export function progressStates(
  status: TicketStatus,
  reached: Iterable<TicketStatus>,
): { step: TicketStatus; state: ProgressState }[] {
  const current = progressIndex(status);
  if (current === -1) return [];
  const seen = new Set(reached);
  return PROGRESS_STEPS.map((step, index) => ({
    step,
    state:
      index === current ? 'current' : index > current ? 'todo' : seen.has(step) ? 'done' : 'skipped',
  }));
}
