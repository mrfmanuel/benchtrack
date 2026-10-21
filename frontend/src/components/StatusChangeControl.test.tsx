import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, api } from '../api/client';
import { TICKET_STATUSES, type Ticket, type TicketStatus } from '../api/types';
import { STATUS_LABELS } from '../lib/statuses';
import { StatusChangeControl } from './StatusChangeControl';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return { ...actual, api: { ...actual.api, changeTicketStatus: vi.fn() } };
});

const changeTicketStatus = vi.mocked(api.changeTicketStatus);

function makeTicket(status: TicketStatus): Ticket {
  return {
    id: 42,
    customer_id: 1,
    customer: { id: 1, name: 'Ana Mora', phone: '+50688001234' },
    device_type: 'laptop',
    brand: 'Lenovo',
    model: 'ThinkPad T14',
    serial_number: null,
    reported_issue: 'Does not turn on.',
    diagnosis: null,
    estimated_cost: null,
    status,
    tracking_code: 'BT-7K3QX',
    created_at: '2026-10-01T15:10:00Z',
    updated_at: '2026-10-01T15:10:00Z',
  };
}

// Spec F3, written out again on purpose.
const EXPECTED: Record<TicketStatus, string[]> = {
  received: ['Diagnosing', 'Cancelled'],
  diagnosing: ['Waiting for parts', 'Repairing', 'Ready for pickup', 'Cancelled'],
  waiting_parts: ['Repairing', 'Cancelled'],
  repairing: ['Waiting for parts', 'Ready for pickup', 'Cancelled'],
  ready: ['Repairing', 'Delivered'],
  delivered: [],
  cancelled: [],
};

function optionLabels() {
  const select = screen.getByLabelText(/new status/i);
  return within(select)
    .getAllByRole('option')
    .filter((option) => !(option as HTMLOptionElement).disabled)
    .map((option) => option.textContent);
}

beforeEach(() => {
  changeTicketStatus.mockReset();
});

describe('StatusChangeControl', () => {
  it.each(TICKET_STATUSES.filter((s) => EXPECTED[s].length > 0))(
    'offers only the allowed next statuses from %s',
    (status) => {
      render(<StatusChangeControl ticket={makeTicket(status)} onChanged={() => {}} />);
      expect(optionLabels()).toEqual(EXPECTED[status]);
      expect(optionLabels()).not.toContain(STATUS_LABELS[status]);
    },
  );

  it.each(['delivered', 'cancelled'] as const)('offers no options when the ticket is %s', (status) => {
    render(<StatusChangeControl ticket={makeTicket(status)} onChanged={() => {}} />);
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /change status/i })).not.toBeInTheDocument();
    expect(screen.getByTestId('status-final')).toHaveTextContent(/can no longer change/i);
  });

  it('disables submit until a status is chosen', async () => {
    render(<StatusChangeControl ticket={makeTicket('received')} onChanged={() => {}} />);
    const submit = screen.getByRole('button', { name: /change status/i });
    expect(submit).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText(/new status/i), 'diagnosing');
    expect(submit).toBeEnabled();
  });

  it('sends the chosen status and note, then reports the updated ticket', async () => {
    const updated = makeTicket('diagnosing');
    changeTicketStatus.mockResolvedValue(updated);
    const onChanged = vi.fn();
    render(<StatusChangeControl ticket={makeTicket('received')} onChanged={onChanged} />);

    await userEvent.selectOptions(screen.getByLabelText(/new status/i), 'diagnosing');
    await userEvent.type(screen.getByLabelText(/note for the timeline/i), '  Checking the board.  ');
    await userEvent.click(screen.getByRole('button', { name: /change status/i }));

    expect(changeTicketStatus).toHaveBeenCalledWith(42, { to_status: 'diagnosing', note: 'Checking the board.' });
    expect(onChanged).toHaveBeenCalledWith(updated);
  });

  it('omits an empty note', async () => {
    changeTicketStatus.mockResolvedValue(makeTicket('cancelled'));
    render(<StatusChangeControl ticket={makeTicket('received')} onChanged={() => {}} />);
    await userEvent.selectOptions(screen.getByLabelText(/new status/i), 'cancelled');
    await userEvent.click(screen.getByRole('button', { name: /change status/i }));
    expect(changeTicketStatus).toHaveBeenCalledWith(42, { to_status: 'cancelled' });
  });

  it('shows a 409 as a readable banner', async () => {
    changeTicketStatus.mockRejectedValue(
      new ApiError(409, 'invalid_transition', 'Cannot change status from received to diagnosing.', {
        from_status: 'ready',
        to_status: 'diagnosing',
        allowed: ['delivered', 'repairing'],
      }),
    );
    const onChanged = vi.fn();
    render(<StatusChangeControl ticket={makeTicket('received')} onChanged={onChanged} />);
    await userEvent.selectOptions(screen.getByLabelText(/new status/i), 'diagnosing');
    await userEvent.click(screen.getByRole('button', { name: /change status/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Status not changed');
    expect(alert).toHaveTextContent('Allowed next statuses: Delivered, Repairing.');
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('shows a note validation error next to the field', async () => {
    changeTicketStatus.mockRejectedValue(
      new ApiError(422, 'validation_error', 'Request validation failed.', [
        { field: 'note', message: 'String should have at most 1000 characters' },
      ]),
    );
    render(<StatusChangeControl ticket={makeTicket('received')} onChanged={() => {}} />);
    await userEvent.selectOptions(screen.getByLabelText(/new status/i), 'diagnosing');
    await userEvent.type(screen.getByLabelText(/note for the timeline/i), 'x');
    await userEvent.click(screen.getByRole('button', { name: /change status/i }));

    const note = screen.getByLabelText(/note for the timeline/i);
    expect(await screen.findByText('String should have at most 1000 characters')).toBeInTheDocument();
    expect(note).toHaveAttribute('aria-invalid', 'true');
    expect(note).toHaveAccessibleDescription('String should have at most 1000 characters');
  });
});
