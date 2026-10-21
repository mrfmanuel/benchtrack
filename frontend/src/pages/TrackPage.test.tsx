import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, api } from '../api/client';
import type { PublicTracking } from '../api/types';
import { TrackPage } from './TrackPage';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return { ...actual, api: { ...actual.api, trackTicket: vi.fn() } };
});

const trackTicket = vi.mocked(api.trackTicket);

const TRACKING: PublicTracking = {
  tracking_code: 'BT-7K3QX',
  device_type: 'laptop',
  brand: 'Lenovo',
  model: 'ThinkPad T14',
  status: 'waiting_parts',
  last_status_change_at: '2026-10-03T14:00:00Z',
  timeline: [
    { status: 'received', at: '2026-10-01T15:10:00Z' },
    { status: 'diagnosing', at: '2026-10-02T09:30:00Z' },
    { status: 'waiting_parts', at: '2026-10-03T14:00:00Z' },
  ],
};

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/track" element={<TrackPage />} />
        <Route path="/track/:code" element={<TrackPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  trackTicket.mockReset();
});

describe('TrackPage', () => {
  it('looks up the code from the URL and renders status, progress and timeline', async () => {
    trackTicket.mockResolvedValue(TRACKING);
    renderAt('/track/BT-7K3QX');

    const result = await screen.findByRole('region', { name: 'BT-7K3QX' });
    expect(trackTicket).toHaveBeenCalledWith('BT-7K3QX');
    expect(within(result).getByText('Lenovo ThinkPad T14 (Laptop)')).toBeInTheDocument();
    expect(within(result).getByText(/waiting for a part/i)).toBeInTheDocument();

    const progress = within(result).getByRole('list', { name: /progress: step 3 of 6/i });
    expect(within(progress).getByText('Waiting for parts').closest('li')).toHaveAttribute('aria-current', 'step');

    const history = within(result).getByRole('list', { name: /status history/i });
    const items = within(history).getAllByRole('listitem');
    expect(items.map((li) => li.querySelector('strong')?.textContent)).toEqual([
      'Received',
      'Diagnosing',
      'Waiting for parts',
    ]);
    expect(items[0].querySelector('time')).toHaveAttribute('datetime', '2026-10-01T15:10:00Z');
  });

  it('shows a friendly message for an unknown code (404)', async () => {
    trackTicket.mockRejectedValue(
      new ApiError(404, 'not_found', 'Tracking code not found.'),
    );
    renderAt('/track/BT-ZZZZZ');

    expect(await screen.findByText('Repair not found')).toBeInTheDocument();
    expect(screen.getByText(/couldn’t find a repair with the code/i)).toHaveTextContent('BT-ZZZZZ');
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });

  it('shows a wait message when rate-limited (429)', async () => {
    trackTicket.mockRejectedValue(
      new ApiError(429, 'rate_limited', 'Too many requests.', undefined, 37),
    );
    renderAt('/track/BT-7K3QX');

    expect(await screen.findByText('Too many lookups')).toBeInTheDocument();
    expect(screen.getByText(/please wait 37 seconds/i)).toBeInTheDocument();
  });

  it('normalizes the code typed in the form and navigates to it', async () => {
    trackTicket.mockResolvedValue(TRACKING);
    renderAt('/track');
    expect(trackTicket).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText('Tracking code'), '  7k3qx ');
    await userEvent.click(screen.getByRole('button', { name: 'Track' }));

    expect(screen.getByTestId('location')).toHaveTextContent('/track/BT-7K3QX');
    expect(await screen.findByRole('region', { name: 'BT-7K3QX' })).toBeInTheDocument();
    expect(trackTicket).toHaveBeenCalledWith('BT-7K3QX');
  });

  it('redirects a lowercase URL to the canonical code before the lookup', async () => {
    trackTicket.mockResolvedValue(TRACKING);
    renderAt('/track/bt-7k3qx');

    expect(await screen.findByRole('region', { name: 'BT-7K3QX' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/track/BT-7K3QX');
    expect(trackTicket).toHaveBeenCalledTimes(1);
    expect(trackTicket).toHaveBeenCalledWith('BT-7K3QX');
  });

  it('rejects malformed input without calling the API', async () => {
    renderAt('/track');
    await userEvent.type(screen.getByLabelText('Tracking code'), 'BT-0O1IL');
    await userEvent.click(screen.getByRole('button', { name: 'Track' }));

    expect(screen.getByText(/tracking codes look like/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Tracking code')).toHaveAttribute('aria-invalid', 'true');
    expect(trackTicket).not.toHaveBeenCalled();
  });

  it('shows not found for an impossible code in the URL without calling the API', () => {
    renderAt('/track/hello');
    expect(screen.getByText('Repair not found')).toBeInTheDocument();
    expect(trackTicket).not.toHaveBeenCalled();
  });

  it('shows a cancelled repair instead of the progress steps', async () => {
    trackTicket.mockResolvedValue({ ...TRACKING, status: 'cancelled' });
    renderAt('/track/BT-7K3QX');
    expect(await screen.findByText('This repair was cancelled.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: /progress/i })).not.toBeInTheDocument();
  });
});
