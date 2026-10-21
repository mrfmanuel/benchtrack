import { describe, expect, it } from 'vitest';

import { allowedFromError, describeError, existingCustomerId, retryMessage } from './errors';

describe('describeError', () => {
  it('lists allowed statuses for invalid_transition', () => {
    const error = {
      code: 'invalid_transition',
      message: 'Cannot change status from received to ready.',
      details: { from_status: 'received', to_status: 'ready', allowed: ['cancelled', 'diagnosing'] },
    };
    expect(describeError(error)).toBe(
      'Cannot change status from received to ready. Allowed next statuses: Cancelled, Diagnosing.',
    );
    expect(allowedFromError(error)).toEqual(['cancelled', 'diagnosing']);
  });

  it('handles invalid_transition without usable details', () => {
    expect(describeError({ code: 'invalid_transition', message: 'Nope.' })).toBe('Nope.');
    expect(
      describeError({ code: 'invalid_transition', message: 'Nope.', details: { allowed: [] } }),
    ).toBe('Nope. Allowed next statuses: none.');
    expect(
      allowedFromError({ code: 'invalid_transition', message: '', details: { allowed: ['bogus', 'ready'] } }),
    ).toEqual(['ready']);
    expect(allowedFromError({ code: 'conflict', message: '' })).toBeNull();
  });

  it('explains ticket_final', () => {
    expect(
      describeError({ code: 'ticket_final', message: 'Ticket BT-7K3QX is delivered and cannot be edited.' }),
    ).toBe('Ticket BT-7K3QX is delivered and cannot be edited. Notes can still be added.');
  });

  it('includes the retry delay for rate_limited', () => {
    expect(describeError({ code: 'rate_limited', message: 'x', retryAfter: 30 })).toBe(
      'Too many requests. Please wait 30 seconds and try again.',
    );
    expect(retryMessage(1)).toBe('Please wait 1 second and try again.');
    expect(retryMessage(null)).toBe('Please wait a minute and try again.');
  });

  it('points to the fields for validation errors and passes others through', () => {
    expect(describeError({ code: 'validation_error', message: 'Request validation failed.' })).toMatch(
      /highlighted fields/,
    );
    expect(describeError({ code: 'not_found', message: 'Ticket not found.' })).toBe('Ticket not found.');
  });
});

describe('existingCustomerId', () => {
  it('reads the duplicate-phone details', () => {
    expect(
      existingCustomerId({ code: 'conflict', message: '', details: { field: 'phone', existing_customer_id: 4 } }),
    ).toBe(4);
    expect(existingCustomerId({ code: 'conflict', message: '' })).toBeNull();
    expect(existingCustomerId({ code: 'not_found', message: '', details: { existing_customer_id: 4 } })).toBeNull();
  });
});
