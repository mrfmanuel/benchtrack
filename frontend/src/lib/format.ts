// Display formatting. The API returns UTC (`...Z`); the UI shows the browser's local time
// (spec §9.21). Money is CRC (₡, spec §9.3).

import { DEVICE_TYPES, type DeviceType } from '../api/types';

const LOCALE = 'en-US';

const moneyFormat = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** `45000.5` → `₡45,000.50`; `null` → `—`. */
export function formatMoney(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || !Number.isFinite(amount)) return '—';
  const sign = amount < 0 ? '-' : '';
  return `${sign}₡${moneyFormat.format(Math.abs(amount))}`;
}

function toDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export interface FormatOptions {
  /** IANA time zone; defaults to the browser's. Tests pin it. */
  timeZone?: string;
}

/** Local date and time, e.g. `Oct 1, 2026, 9:10 AM`. */
export function formatDateTime(value: string | Date, { timeZone }: FormatOptions = {}): string {
  const date = toDate(value);
  if (!date) return '—';
  return new Intl.DateTimeFormat(LOCALE, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(date);
}

/** Local date only, e.g. `Oct 1, 2026`. */
export function formatDate(value: string | Date, { timeZone }: FormatOptions = {}): string {
  const date = toDate(value);
  if (!date) return '—';
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: 'medium', timeZone }).format(date);
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** Whole days between `value` and `now`, e.g. for "idle for 9 days". */
export function daysSince(value: string | Date, now: Date = new Date()): number {
  const date = toDate(value);
  if (!date) return 0;
  return Math.max(0, Math.floor((now.getTime() - date.getTime()) / DAY_MS));
}

export const DEVICE_TYPE_LABELS: Readonly<Record<DeviceType, string>> = {
  laptop: 'Laptop',
  desktop: 'Desktop',
  phone: 'Phone',
  tablet: 'Tablet',
  printer: 'Printer',
  other: 'Other',
};

export const DEVICE_TYPE_OPTIONS = DEVICE_TYPES.map((value) => ({
  value,
  label: DEVICE_TYPE_LABELS[value],
}));

/** `Lenovo ThinkPad T14 (Laptop)`; model is optional. */
export function formatDevice(device: {
  device_type: DeviceType;
  brand: string;
  model: string | null;
}): string {
  const name = [device.brand, device.model].filter(Boolean).join(' ');
  return `${name} (${DEVICE_TYPE_LABELS[device.device_type]})`;
}
