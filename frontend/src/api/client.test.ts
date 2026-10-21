import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getToken, setToken } from '../lib/tokenStore';
import { ApiError, api, buildQuery, setUnauthorizedHandler } from './client';

const TOKEN = 'fictional-staff-token-1234';

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...headers },
  });
}

const fetchMock = vi.fn<typeof fetch>();
const onUnauthorized = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  onUnauthorized.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  setUnauthorizedHandler(onUnauthorized);
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: String(url), init: init!, headers: init!.headers as Record<string, string> };
}

async function catchApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error('expected the request to fail');
}

describe('auth header', () => {
  it('sends the stored bearer token on staff endpoints', async () => {
    setToken(TOKEN);
    fetchMock.mockImplementation(async () => jsonResponse(200, { items: [], total: 0 }));
    await api.listCustomers();
    expect(lastCall().url).toBe('/api/customers');
    expect(lastCall().headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it('sends no Authorization header without a token', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, { items: [], total: 0 }));
    await api.listTickets();
    expect(lastCall().headers).not.toHaveProperty('Authorization');
  });

  it('never sends the token to the public endpoint', async () => {
    setToken(TOKEN);
    fetchMock.mockImplementation(async () => jsonResponse(200, {}));
    await api.trackTicket('BT-7K3QX');
    expect(lastCall().url).toBe('/api/public/track/BT-7K3QX');
    expect(lastCall().headers).not.toHaveProperty('Authorization');
  });

  it('can validate an explicit token before it is stored', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, { counts: {}, stale_tickets: [] }));
    await api.getDashboard('candidate-token-123456');
    expect(lastCall().url).toBe('/api/dashboard');
    expect(lastCall().headers.Authorization).toBe('Bearer candidate-token-123456');
  });
});

describe('requests', () => {
  beforeEach(() => setToken(TOKEN));

  it('sends JSON bodies with the right method and path', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, { id: 42 }));
    await api.changeTicketStatus(42, { to_status: 'diagnosing', note: 'Checking.' });
    const { url, init, headers } = lastCall();
    expect(url).toBe('/api/tickets/42/status');
    expect(init.method).toBe('POST');
    expect(headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toEqual({ to_status: 'diagnosing', note: 'Checking.' });
  });

  it.each([
    ['getCustomer', () => api.getCustomer(3), 'GET', '/api/customers/3'],
    ['updateCustomer', () => api.updateCustomer(3, { name: 'X' }), 'PATCH', '/api/customers/3'],
    ['createCustomer', () => api.createCustomer({ name: 'X', phone: '88001234' }), 'POST', '/api/customers'],
    ['createTicket', () => api.createTicket({ customer_id: 1, device_type: 'laptop', brand: 'HP', reported_issue: 'x' }), 'POST', '/api/tickets'],
    ['getTicket', () => api.getTicket(7), 'GET', '/api/tickets/7'],
    ['updateTicket', () => api.updateTicket(7, { brand: 'HP' }), 'PATCH', '/api/tickets/7'],
    ['addTicketNote', () => api.addTicketNote(7, { note: 'x' }), 'POST', '/api/tickets/7/notes'],
    ['listTicketEvents', () => api.listTicketEvents(7), 'GET', '/api/tickets/7/events'],
    ['getHealth', () => api.getHealth(), 'GET', '/api/health'],
  ] as const)('%s → %s %s', async (_name, call, method, path) => {
    fetchMock.mockImplementation(async () => jsonResponse(200, {}));
    await call();
    expect(lastCall().init.method).toBe(method);
    expect(lastCall().url).toBe(path);
  });

  it('URL-encodes the tracking code', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, {}));
    await api.trackTicket('bt 7k/3qx');
    expect(lastCall().url).toBe('/api/public/track/bt%207k%2F3qx');
  });

  it('returns the parsed JSON body', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, { items: [{ id: 1 }], total: 1 }));
    await expect(api.listCustomers()).resolves.toEqual({ items: [{ id: 1 }], total: 1 });
  });
});

describe('query params', () => {
  it('serializes ticket filters and skips empty values', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, { items: [], total: 0 }));
    await api.listTickets({ status: 'ready', q: 'Ana Mora', customer_id: 3, limit: 20, offset: 40 });
    expect(lastCall().url).toBe(
      '/api/tickets?status=ready&q=Ana+Mora&customer_id=3&limit=20&offset=40',
    );

    await api.listTickets({ status: undefined, q: '', offset: 0 });
    expect(lastCall().url).toBe('/api/tickets?offset=0');
  });

  it('serializes customer search', async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, { items: [], total: 0 }));
    await api.listCustomers({ q: 'Jiménez & co', limit: 10 });
    expect(lastCall().url).toBe('/api/customers?q=Jim%C3%A9nez+%26+co&limit=10');
  });

  it('buildQuery handles empty input', () => {
    expect(buildQuery()).toBe('');
    expect(buildQuery({ a: null, b: undefined, c: '' })).toBe('');
    expect(buildQuery({ a: 0 })).toBe('?a=0');
  });
});

describe('error envelope parsing', () => {
  beforeEach(() => setToken(TOKEN));

  it('parses validation errors and exposes fieldErrors', async () => {
    fetchMock.mockImplementation(async () => 
      jsonResponse(422, {
        error: {
          code: 'validation_error',
          message: 'Request validation failed.',
          details: [
            { field: 'phone', message: 'Phone must contain 8 to 15 digits.' },
            { bogus: true },
          ],
        },
      }),
    );
    const error = await catchApiError(api.createCustomer({ name: 'Ana', phone: '12' }));
    expect(error.status).toBe(422);
    expect(error.code).toBe('validation_error');
    expect(error.message).toBe('Request validation failed.');
    expect(error.fieldErrors).toEqual([
      { field: 'phone', message: 'Phone must contain 8 to 15 digits.' },
    ]);
  });

  it('parses 409 invalid_transition details', async () => {
    const details = { from_status: 'received', to_status: 'ready', allowed: ['cancelled', 'diagnosing'] };
    fetchMock.mockImplementation(async () => 
      jsonResponse(409, {
        error: { code: 'invalid_transition', message: 'Cannot change status from received to ready.', details },
      }),
    );
    const error = await catchApiError(api.changeTicketStatus(1, { to_status: 'ready' }));
    expect(error.status).toBe(409);
    expect(error.code).toBe('invalid_transition');
    expect(error.details).toEqual(details);
    expect(error.fieldErrors).toEqual([]);
  });

  it('reads Retry-After on 429', async () => {
    fetchMock.mockImplementation(async () => 
      jsonResponse(
        429,
        { error: { code: 'rate_limited', message: 'Too many requests.' } },
        { 'Retry-After': '42' },
      ),
    );
    const error = await catchApiError(api.trackTicket('BT-7K3QX'));
    expect(error.code).toBe('rate_limited');
    expect(error.retryAfter).toBe(42);
  });

  it('falls back for non-JSON or non-envelope bodies', async () => {
    fetchMock.mockImplementation(async () => new Response('<html>Bad gateway</html>', { status: 502 }));
    const error = await catchApiError(api.getTicket(1));
    expect(error.status).toBe(502);
    expect(error.code).toBe('http_error');
    expect(error.message).toBe('Request failed with status 502.');

    fetchMock.mockImplementation(async () => jsonResponse(503, { status: 'degraded', database: 'error' }));
    expect((await catchApiError(api.getHealth())).code).toBe('http_error');
  });

  it('turns network failures into network_error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const error = await catchApiError(api.getDashboard());
    expect(error.status).toBe(0);
    expect(error.code).toBe('network_error');
  });
});

describe('401 handling', () => {
  const unauthorized = () =>
    jsonResponse(
      401,
      { error: { code: 'unauthorized', message: 'Missing or invalid staff token.' } },
      { 'WWW-Authenticate': 'Bearer' },
    );

  it('clears the stored token, calls the redirect handler and still rejects', async () => {
    setToken(TOKEN);
    fetchMock.mockImplementation(async () => unauthorized());
    const error = await catchApiError(api.listTickets());
    expect(error.status).toBe(401);
    expect(error.code).toBe('unauthorized');
    expect(getToken()).toBeNull();
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it('does not treat other errors as sign-out', async () => {
    setToken(TOKEN);
    fetchMock.mockImplementation(async () => jsonResponse(404, { error: { code: 'not_found', message: 'Ticket not found.' } }));
    await catchApiError(api.getTicket(99));
    expect(getToken()).toBe(TOKEN);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
