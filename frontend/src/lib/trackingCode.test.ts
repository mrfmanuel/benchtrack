import { describe, expect, it } from 'vitest';

import {
  TRACKING_ALPHABET,
  isValidTrackingCode,
  normalizeTrackingCode,
  trackingUrl,
} from './trackingCode';

describe('normalizeTrackingCode', () => {
  it.each([
    ['BT-7K3QX', 'BT-7K3QX'],
    ['bt-7k3qx', 'BT-7K3QX'],
    ['  BT-7K3QX\t', 'BT-7K3QX'],
    ['7k3qx', 'BT-7K3QX'],
    [' 7K3QX ', 'BT-7K3QX'],
    ['Bt-dem22', 'BT-DEM22'],
  ])('%j → %s', (input, expected) => {
    expect(normalizeTrackingCode(input)).toBe(expected);
  });

  it.each([
    [''],
    ['   '],
    ['BT-'],
    ['BT7K3QX'], // missing dash
    ['BT-7K3Q'], // too short
    ['BT-7K3QXX'], // too long
    ['BT-7K 3Q'], // inner whitespace
    ['BT-0K3QX'], // 0 excluded
    ['BT-OK3QX'], // O excluded
    ['BT-1K3QX'], // 1 excluded
    ['BT-IK3QX'], // I excluded
    ['BT-LK3QX'], // L excluded
    ['BT-UK3QX'], // U excluded
    ['XX-7K3QX'],
    ['BT_7K3QX'],
  ])('rejects %j', (input) => {
    expect(normalizeTrackingCode(input)).toBeNull();
  });
});

describe('isValidTrackingCode', () => {
  it('accepts only canonical codes', () => {
    expect(isValidTrackingCode('BT-7K3QX')).toBe(true);
    expect(isValidTrackingCode('bt-7k3qx')).toBe(false);
    expect(isValidTrackingCode('7K3QX')).toBe(false);
  });

  it('uses the spec alphabet (no 0, O, 1, I, L, U)', () => {
    expect(TRACKING_ALPHABET).toBe('23456789ABCDEFGHJKMNPQRSTVWXYZ');
    for (const c of '0O1ILU') expect(TRACKING_ALPHABET).not.toContain(c);
  });
});

describe('trackingUrl', () => {
  it('builds the public URL', () => {
    expect(trackingUrl('BT-7K3QX', 'https://shop.example.com')).toBe(
      'https://shop.example.com/track/BT-7K3QX',
    );
  });

  it('defaults to the current origin', () => {
    expect(trackingUrl('BT-7K3QX')).toBe(`${window.location.origin}/track/BT-7K3QX`);
  });
});
