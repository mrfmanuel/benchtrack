import { describe, expect, it } from 'vitest';

import type { Ticket } from '../api/types';
import { changedFields } from './forms';
import { EMPTY_TICKET_FORM, formValuesToPayload, ticketToFormValues } from './ticketForm';

const ticket: Ticket = {
  id: 42,
  customer_id: 1,
  customer: { id: 1, name: 'Ana Mora', phone: '+50688001234' },
  device_type: 'laptop',
  brand: 'Lenovo',
  model: 'ThinkPad T14',
  serial_number: null,
  reported_issue: 'Does not turn on after a coffee spill.',
  diagnosis: null,
  estimated_cost: 45000.5,
  status: 'diagnosing',
  tracking_code: 'BT-7K3QX',
  created_at: '2026-10-01T15:10:00Z',
  updated_at: '2026-10-02T09:30:00Z',
};

describe('ticket form conversion', () => {
  it('round-trips a ticket without changes', () => {
    const result = formValuesToPayload(ticketToFormValues(ticket));
    expect('payload' in result).toBe(true);
    if (!('payload' in result)) return;
    expect(changedFields(ticket, result.payload)).toEqual({});
  });

  it('trims text, nulls optional blanks and parses the cost', () => {
    const result = formValuesToPayload({
      ...EMPTY_TICKET_FORM,
      device_type: 'phone',
      brand: '  Samsung ',
      model: ' ',
      reported_issue: ' Cracked screen ',
      estimated_cost: '12,500',
    });
    expect(result).toEqual({
      payload: {
        device_type: 'phone',
        brand: 'Samsung',
        model: null,
        serial_number: null,
        reported_issue: 'Cracked screen',
        diagnosis: null,
        estimated_cost: 12500,
      },
    });
  });

  it('keeps blank required fields for the server to reject', () => {
    const result = formValuesToPayload(EMPTY_TICKET_FORM);
    expect(result).toMatchObject({ payload: { brand: '', reported_issue: '' } });
  });

  it('reports an unparsable cost as a field error', () => {
    expect(formValuesToPayload({ ...EMPTY_TICKET_FORM, estimated_cost: 'cheap' })).toEqual({
      errors: { estimated_cost: expect.stringMatching(/colones/) },
    });
  });
});
