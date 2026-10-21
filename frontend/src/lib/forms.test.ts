import { describe, expect, it } from 'vitest';

import { INVALID_COST_MESSAGE, blankToNull, changedFields, parseCost, splitFieldErrors } from './forms';

describe('splitFieldErrors', () => {
  it('maps known fields and collects the rest', () => {
    const result = splitFieldErrors(
      [
        { field: 'phone', message: 'Phone must contain 8 to 15 digits.' },
        { field: 'name', message: 'Required.' },
        { field: 'body', message: 'At least one field is required.' },
      ],
      ['name', 'phone', 'email'],
    );
    expect(result.fields).toEqual({
      phone: 'Phone must contain 8 to 15 digits.',
      name: 'Required.',
    });
    expect(result.other).toEqual(['At least one field is required.']);
  });

  it('joins several messages for one field', () => {
    const { fields } = splitFieldErrors(
      [
        { field: 'brand', message: 'Too long.' },
        { field: 'brand', message: 'Invalid.' },
      ],
      ['brand'],
    );
    expect(fields.brand).toBe('Too long. Invalid.');
  });
});

describe('blankToNull', () => {
  it('trims and nulls blanks', () => {
    expect(blankToNull('  ThinkPad ')).toBe('ThinkPad');
    expect(blankToNull('   ')).toBeNull();
    expect(blankToNull('')).toBeNull();
  });
});

describe('parseCost', () => {
  it.each<[string, number | null]>([
    ['', null],
    ['  ', null],
    ['₡', null],
    ['0', 0],
    ['45000.5', 45000.5],
    ['45,000.50', 45000.5],
    ['₡ 12 500', 12500],
    ['-5', -5], // range is validated by the server
  ])('%j → %j', (input, expected) => {
    expect(parseCost(input)).toEqual({ value: expected });
  });

  it.each(['abc', '12.', '1e3', '12.5.1', '₡x'])('rejects %j', (input) => {
    expect(parseCost(input)).toEqual({ error: INVALID_COST_MESSAGE });
  });
});

describe('changedFields', () => {
  it('keeps only changed keys', () => {
    const original = { brand: 'HP', model: null as string | null, estimated_cost: 100 as number | null };
    expect(changedFields(original, { brand: 'HP', model: 'EliteBook', estimated_cost: null })).toEqual({
      model: 'EliteBook',
      estimated_cost: null,
    });
    expect(changedFields(original, { brand: 'HP' })).toEqual({});
  });
});
