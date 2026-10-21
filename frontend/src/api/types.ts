// API payload types. Must match `openapi.yaml` (components/schemas) exactly:
// update both in the same change.

export const TICKET_STATUSES = [
  'received',
  'diagnosing',
  'waiting_parts',
  'repairing',
  'ready',
  'delivered',
  'cancelled',
] as const;
export type TicketStatus = (typeof TICKET_STATUSES)[number];

export const DEVICE_TYPES = ['laptop', 'desktop', 'phone', 'tablet', 'printer', 'other'] as const;
export type DeviceType = (typeof DEVICE_TYPES)[number];

/** UTC, ISO 8601 with `Z` suffix. */
export type Timestamp = string;

/** `{"error": {code, message, details?}}` — every error except the health 503. */
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

/** `details` of a `validation_error`. */
export interface FieldErrorDetail {
  field: string;
  message: string;
}

/** `details` of an `invalid_transition` (409). */
export interface InvalidTransitionDetails {
  from_status: TicketStatus;
  to_status: TicketStatus;
  allowed: TicketStatus[];
}

/** `details` of a duplicate-phone `conflict` (409). */
export interface DuplicatePhoneDetails {
  field: 'phone';
  existing_customer_id: number;
}

export interface Health {
  status: 'ok' | 'degraded';
  database: 'ok' | 'error';
}

export interface Page<T> {
  items: T[];
  total: number;
}

// --- Customers ---

export interface Customer {
  id: number;
  name: string;
  phone: string;
  email: string | null;
  created_at: Timestamp;
}

export interface CustomerSummary {
  id: number;
  name: string;
  phone: string;
}

export interface CustomerCreate {
  name: string;
  phone: string;
  email?: string | null;
}

/** At least one field (`minProperties: 1`). */
export type CustomerUpdate = Partial<CustomerCreate>;

export type CustomerList = Page<Customer>;

export interface CustomerListParams {
  q?: string;
  limit?: number;
  offset?: number;
}

// --- Tickets ---

export interface Ticket {
  id: number;
  customer_id: number;
  customer: CustomerSummary;
  device_type: DeviceType;
  brand: string;
  model: string | null;
  serial_number: string | null;
  reported_issue: string;
  diagnosis: string | null;
  /** CRC (₡), 2 decimals, 0–10,000,000. */
  estimated_cost: number | null;
  status: TicketStatus;
  tracking_code: string;
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface TicketCreate {
  customer_id: number;
  device_type: DeviceType;
  brand: string;
  reported_issue: string;
  model?: string | null;
  serial_number?: string | null;
  diagnosis?: string | null;
  estimated_cost?: number | null;
}

/** `customer_id`, `status` and `tracking_code` are not accepted; at least one field. */
export type TicketUpdate = Partial<Omit<TicketCreate, 'customer_id'>>;

export type TicketList = Page<Ticket>;

export interface TicketListParams {
  customer_id?: number;
  status?: TicketStatus;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface StatusChange {
  to_status: TicketStatus;
  note?: string;
}

export interface NoteCreate {
  note: string;
}

// --- Timeline ---

export interface TicketEvent {
  id: number;
  ticket_id: number;
  kind: 'status' | 'note';
  from_status: TicketStatus | null;
  to_status: TicketStatus | null;
  note: string | null;
  created_at: Timestamp;
}

export type TicketEventList = Page<TicketEvent>;

// --- Dashboard ---

export type StatusCounts = Record<TicketStatus, number>;

export interface Dashboard {
  counts: StatusCounts;
  stale_tickets: Ticket[];
}

// --- Public ---

export interface PublicTimelineEntry {
  status: TicketStatus;
  at: Timestamp;
}

/** Exact public whitelist (spec 9.15). */
export interface PublicTracking {
  tracking_code: string;
  device_type: DeviceType;
  brand: string;
  model: string | null;
  status: TicketStatus;
  last_status_change_at: Timestamp;
  timeline: PublicTimelineEntry[];
}
