// The only module that talks HTTP. Components call these functions, never `fetch`.

import { clearToken, getToken } from '../lib/tokenStore';
import type {
  Customer,
  CustomerCreate,
  CustomerList,
  CustomerListParams,
  CustomerUpdate,
  Dashboard,
  FieldErrorDetail,
  Health,
  NoteCreate,
  PublicTracking,
  StatusChange,
  Ticket,
  TicketCreate,
  TicketEvent,
  TicketEventList,
  TicketList,
  TicketListParams,
  TicketUpdate,
} from './types';

export const API_BASE = '/api';
export const EXPIRED_TOKEN_MESSAGE = 'Invalid or expired token';

/** A failed request, parsed from the `{"error": {...}}` envelope when there is one. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  /** Seconds from the `Retry-After` header (429 only). */
  readonly retryAfter: number | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.retryAfter = retryAfter;
  }

  /** `details` of a `validation_error`, or `[]`. */
  get fieldErrors(): FieldErrorDetail[] {
    if (this.code !== 'validation_error' || !Array.isArray(this.details)) return [];
    return this.details.filter(
      (d): d is FieldErrorDetail =>
        typeof d === 'object' &&
        d !== null &&
        typeof (d as FieldErrorDetail).field === 'string' &&
        typeof (d as FieldErrorDetail).message === 'string',
    );
  }
}

type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler = () => {
  window.location.assign('/sign-in');
};

/** The app installs a router-aware handler; the default does a full-page redirect. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  onUnauthorized = handler;
}

type QueryValue = string | number | undefined | null;

export function buildQuery(params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH';
  body?: unknown;
  query?: Record<string, QueryValue>;
  /** Staff endpoints send the bearer token; public ones never do. */
  auth?: boolean;
  /** Override the stored token (sign-in validates a token before saving it). */
  token?: string;
  /** Non-2xx statuses whose body is a normal response (the health check's `503`). */
  bodyStatuses?: number[];
}

function isErrorEnvelope(value: unknown): value is { error: { code: string; message: string; details?: unknown } } {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code: unknown }).code === 'string' &&
    typeof (error as { message: unknown }).message === 'string'
  );
}

function parseRetryAfter(response: Response): number | null {
  const raw = response.headers.get('Retry-After');
  if (raw === null) return null;
  const seconds = Number.parseInt(raw, 10);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON (e.g. a proxy error page).
  }
  const retryAfter = parseRetryAfter(response);
  if (isErrorEnvelope(body)) {
    const { code, message, details } = body.error;
    return new ApiError(response.status, code, message, details, retryAfter);
  }
  return new ApiError(
    response.status,
    'http_error',
    `Request failed with status ${response.status}.`,
    undefined,
    retryAfter,
  );
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, auth = true, bodyStatuses = [] } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth) {
    const token = options.token ?? getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}${buildQuery(query)}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Check your connection.');
  }

  if (!response.ok && !bodyStatuses.includes(response.status)) {
    const error = await toApiError(response);
    if (response.status === 401 && auth) {
      clearToken();
      onUnauthorized();
    }
    throw error;
  }
  return (await response.json()) as T;
}

// --- Endpoints (one per operationId in openapi.yaml) ---

export const api = {
  // `503` carries a `Health` body (`status: degraded`), not the error envelope.
  getHealth: () => request<Health>('/health', { auth: false, bodyStatuses: [503] }),

  listCustomers: (params: CustomerListParams = {}) =>
    request<CustomerList>('/customers', { query: { ...params } }),
  createCustomer: (data: CustomerCreate) =>
    request<Customer>('/customers', { method: 'POST', body: data }),
  getCustomer: (id: number) => request<Customer>(`/customers/${id}`),
  updateCustomer: (id: number, data: CustomerUpdate) =>
    request<Customer>(`/customers/${id}`, { method: 'PATCH', body: data }),

  listTickets: (params: TicketListParams = {}) =>
    request<TicketList>('/tickets', { query: { ...params } }),
  createTicket: (data: TicketCreate) => request<Ticket>('/tickets', { method: 'POST', body: data }),
  getTicket: (id: number) => request<Ticket>(`/tickets/${id}`),
  updateTicket: (id: number, data: TicketUpdate) =>
    request<Ticket>(`/tickets/${id}`, { method: 'PATCH', body: data }),
  changeTicketStatus: (id: number, data: StatusChange) =>
    request<Ticket>(`/tickets/${id}/status`, { method: 'POST', body: data }),
  addTicketNote: (id: number, data: NoteCreate) =>
    request<TicketEvent>(`/tickets/${id}/notes`, { method: 'POST', body: data }),
  listTicketEvents: (id: number) => request<TicketEventList>(`/tickets/${id}/events`),

  getDashboard: (token?: string) => request<Dashboard>('/dashboard', { token }),

  trackTicket: (code: string) =>
    request<PublicTracking>(`/public/track/${encodeURIComponent(code)}`, { auth: false }),
};
