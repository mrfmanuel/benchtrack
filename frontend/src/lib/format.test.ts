import { describe, expect, it } from 'vitest';

import { DEVICE_TYPES } from '../api/types';
import {
  DEVICE_TYPE_LABELS,
  DEVICE_TYPE_OPTIONS,
  daysSince,
  formatDate,
  formatDateTime,
  formatDevice,
  formatMoney,
} from './format';

describe('formatMoney', () => {
  it.each<[number, string]>([
    [0, '₡0.00'],
    [45000.5, '₡45,000.50'],
    [1234567.891, '₡1,234,567.89'],
    [10_000_000, '₡10,000,000.00'],
    [-15, '-₡15.00'],
  ])('%s → %s', (amount, expected) => {
    expect(formatMoney(amount)).toBe(expected);
  });

  it('shows a dash for missing values', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney(Number.NaN)).toBe('—');
  });
});

describe('formatDateTime / formatDate', () => {
  const utc = '2026-10-01T15:10:00Z';

  it('converts UTC to the given local time zone', () => {
    // Costa Rica is UTC-6 all year.
    expect(formatDateTime(utc, { timeZone: 'America/Costa_Rica' })).toBe('Oct 1, 2026, 9:10 AM');
    expect(formatDateTime(utc, { timeZone: 'UTC' })).toBe('Oct 1, 2026, 3:10 PM');
    expect(formatDateTime(utc, { timeZone: 'Asia/Tokyo' })).toBe('Oct 2, 2026, 12:10 AM');
  });

  it('can change the calendar date', () => {
    expect(formatDate('2026-10-01T03:00:00Z', { timeZone: 'America/Costa_Rica' })).toBe(
      'Sep 30, 2026',
    );
    expect(formatDate('2026-10-01T03:00:00Z', { timeZone: 'UTC' })).toBe('Oct 1, 2026');
  });

  it('accepts Date objects and defaults to the browser time zone', () => {
    const date = new Date(utc);
    expect(formatDateTime(date)).toBe(
      new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(date),
    );
  });

  it('shows a dash for invalid input', () => {
    expect(formatDateTime('not a date')).toBe('—');
    expect(formatDate('')).toBe('—');
  });
});

describe('daysSince', () => {
  const now = new Date('2026-10-20T12:00:00Z');

  it('counts whole days', () => {
    expect(daysSince('2026-10-20T00:00:00Z', now)).toBe(0);
    expect(daysSince('2026-10-12T11:59:59Z', now)).toBe(8);
    expect(daysSince('2026-10-12T12:00:01Z', now)).toBe(7);
  });

  it('never goes negative and tolerates bad input', () => {
    expect(daysSince('2026-10-21T00:00:00Z', now)).toBe(0);
    expect(daysSince('garbage', now)).toBe(0);
  });
});

describe('devices', () => {
  it('labels every device type', () => {
    expect(Object.keys(DEVICE_TYPE_LABELS).sort()).toEqual([...DEVICE_TYPES].sort());
    expect(DEVICE_TYPE_OPTIONS.map((o) => o.value)).toEqual([...DEVICE_TYPES]);
  });

  it('formats brand, optional model and type', () => {
    expect(formatDevice({ device_type: 'laptop', brand: 'Lenovo', model: 'ThinkPad T14' })).toBe(
      'Lenovo ThinkPad T14 (Laptop)',
    );
    expect(formatDevice({ device_type: 'printer', brand: 'Epson', model: null })).toBe(
      'Epson (Printer)',
    );
  });
});
