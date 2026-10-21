// Ticket form values (all strings, as typed) ↔ API payloads.

import type { DeviceType, Ticket, TicketUpdate } from '../api/types';
import { blankToNull, parseCost } from './forms';

export interface TicketFormValues {
  device_type: DeviceType;
  brand: string;
  model: string;
  serial_number: string;
  reported_issue: string;
  diagnosis: string;
  estimated_cost: string;
}

export const TICKET_FORM_FIELDS = [
  'device_type',
  'brand',
  'model',
  'serial_number',
  'reported_issue',
  'diagnosis',
  'estimated_cost',
] as const;

export const EMPTY_TICKET_FORM: TicketFormValues = {
  device_type: 'laptop',
  brand: '',
  model: '',
  serial_number: '',
  reported_issue: '',
  diagnosis: '',
  estimated_cost: '',
};

export function ticketToFormValues(ticket: Ticket): TicketFormValues {
  return {
    device_type: ticket.device_type,
    brand: ticket.brand,
    model: ticket.model ?? '',
    serial_number: ticket.serial_number ?? '',
    reported_issue: ticket.reported_issue,
    diagnosis: ticket.diagnosis ?? '',
    estimated_cost: ticket.estimated_cost === null ? '' : String(ticket.estimated_cost),
  };
}

export type TicketPayloadResult =
  | { payload: Required<TicketUpdate> }
  | { errors: Record<string, string> };

/**
 * Required text is sent trimmed even when blank, so the server's validation message is
 * shown; optional blanks become `null`.
 */
export function formValuesToPayload(values: TicketFormValues): TicketPayloadResult {
  const cost = parseCost(values.estimated_cost);
  if ('error' in cost) return { errors: { estimated_cost: cost.error } };
  return {
    payload: {
      device_type: values.device_type,
      brand: values.brand.trim(),
      model: blankToNull(values.model),
      serial_number: blankToNull(values.serial_number),
      reported_issue: values.reported_issue.trim(),
      diagnosis: blankToNull(values.diagnosis),
      estimated_cost: cost.value,
    },
  };
}
