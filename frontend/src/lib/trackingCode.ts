// Tracking-code input normalization, mirroring the server rules (spec §9.12–9.13):
// case-insensitive, surrounding whitespace trimmed, `BT-` prefix optional.
// The server normalizes too; this keeps URLs canonical and catches typos early.

export const TRACKING_ALPHABET = '23456789ABCDEFGHJKMNPQRSTVWXYZ';
export const TRACKING_PREFIX = 'BT-';

const CODE_RE = new RegExp(`^BT-[${TRACKING_ALPHABET}]{5}$`);
const BODY_RE = new RegExp(`^[${TRACKING_ALPHABET}]{5}$`);

export function isValidTrackingCode(code: string): boolean {
  return CODE_RE.test(code);
}

/**
 * `' bt-7k3qx '` / `'7k3qx'` → `'BT-7K3QX'`. Returns `null` when the input cannot be a
 * tracking code (wrong length, excluded characters such as 0/O/1/I/L/U, missing dash).
 */
export function normalizeTrackingCode(input: string): string | null {
  const upper = input.trim().toUpperCase();
  const body = upper.startsWith(TRACKING_PREFIX) ? upper.slice(TRACKING_PREFIX.length) : upper;
  return BODY_RE.test(body) ? `${TRACKING_PREFIX}${body}` : null;
}

/** Public tracking URL printed on the receipt. */
export function trackingUrl(code: string, origin: string = window.location.origin): string {
  return `${origin}/track/${code}`;
}
