import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { TICKET_STATUSES, type TicketStatus } from '../api/types';
import {
  ALLOWED_TRANSITIONS,
  FINAL_STATUSES,
  OPEN_STATUSES,
  PROGRESS_STEPS,
  STATUS_DESCRIPTIONS,
  STATUS_LABELS,
  STATUS_TONES,
  allowedNextStatuses,
  isFinal,
  isTransitionAllowed,
  progressIndex,
  progressStates,
} from './statuses';

// The table is read from the spec and the contract themselves (lines like
// "- `received → diagnosing | cancelled`"), so it is encoded independently of statuses.ts.
const REPO_ROOT = resolve(import.meta.dirname, '../../..');

function parseTransitionTable(file: string): Record<string, string[]> {
  const text = readFileSync(resolve(REPO_ROOT, file), 'utf8');
  const table: Record<string, string[]> = {};
  for (const match of text.matchAll(/^\s*- `([a-z_]+) → ([a-z_ |]+)`\s*$/gm)) {
    table[match[1]] = match[2].split('|').map((s) => s.trim());
  }
  const finals = text.match(/^\s*- `([a-z_]+)`, `([a-z_]+)` are final\./m);
  expect(finals, `final statuses line in ${file}`).not.toBeNull();
  for (const status of [finals![1], finals![2]]) table[status] = [];
  return table;
}

const normalize = (table: Record<string, readonly string[]>) =>
  Object.fromEntries(Object.entries(table).map(([k, v]) => [k, [...v].sort()]));

describe('ALLOWED_TRANSITIONS', () => {
  it.each(['product-spec.md', 'openapi.yaml'])('matches the table in %s', (file) => {
    const table = parseTransitionTable(file);
    expect(Object.keys(table).sort()).toEqual([...TICKET_STATUSES].sort());
    expect(normalize(ALLOWED_TRANSITIONS)).toEqual(normalize(table));
  });

  it('never allows a change to the same status (spec 9.9)', () => {
    for (const status of TICKET_STATUSES) {
      expect(isTransitionAllowed(status, status)).toBe(false);
    }
  });

  it('only targets known statuses', () => {
    for (const targets of Object.values(ALLOWED_TRANSITIONS)) {
      for (const target of targets) expect(TICKET_STATUSES).toContain(target);
    }
  });
});

describe('allowedNextStatuses', () => {
  it.each<[TicketStatus, TicketStatus[]]>([
    ['received', ['diagnosing', 'cancelled']],
    ['diagnosing', ['waiting_parts', 'repairing', 'ready', 'cancelled']],
    ['waiting_parts', ['repairing', 'cancelled']],
    ['repairing', ['waiting_parts', 'ready', 'cancelled']],
    ['ready', ['repairing', 'delivered']],
    ['delivered', []],
    ['cancelled', []],
  ])('%s → %j in workflow order', (status, expected) => {
    expect(allowedNextStatuses(status)).toEqual(expected);
  });

  it('returns a copy that callers may mutate', () => {
    allowedNextStatuses('received').push('ready');
    expect(allowedNextStatuses('received')).toEqual(['diagnosing', 'cancelled']);
  });
});

describe('isTransitionAllowed', () => {
  it('accepts allowed and rejects other transitions', () => {
    expect(isTransitionAllowed('received', 'diagnosing')).toBe(true);
    expect(isTransitionAllowed('ready', 'repairing')).toBe(true);
    expect(isTransitionAllowed('received', 'ready')).toBe(false);
    expect(isTransitionAllowed('delivered', 'repairing')).toBe(false);
    expect(isTransitionAllowed('cancelled', 'received')).toBe(false);
  });
});

describe('final and open statuses', () => {
  it('delivered and cancelled are final, the rest open', () => {
    expect([...FINAL_STATUSES].sort()).toEqual(['cancelled', 'delivered']);
    expect(OPEN_STATUSES).toEqual(['received', 'diagnosing', 'waiting_parts', 'repairing', 'ready']);
    expect(isFinal('delivered')).toBe(true);
    expect(isFinal('cancelled')).toBe(true);
    expect(isFinal('ready')).toBe(false);
  });

  it('final statuses are exactly those without outgoing transitions', () => {
    for (const status of TICKET_STATUSES) {
      expect(isFinal(status)).toBe(ALLOWED_TRANSITIONS[status].length === 0);
    }
  });
});

describe('labels, descriptions and tones', () => {
  it('cover every status', () => {
    for (const status of TICKET_STATUSES) {
      expect(STATUS_LABELS[status]).toMatch(/\S/);
      expect(STATUS_DESCRIPTIONS[status]).toMatch(/\S/);
      expect(STATUS_TONES[status]).toMatch(/^[a-z]+$/);
    }
  });

  it('uses distinct labels and tones', () => {
    expect(new Set(Object.values(STATUS_LABELS)).size).toBe(TICKET_STATUSES.length);
    expect(new Set(Object.values(STATUS_TONES)).size).toBe(TICKET_STATUSES.length);
  });

  it('has readable labels', () => {
    expect(STATUS_LABELS.waiting_parts).toBe('Waiting for parts');
    expect(STATUS_LABELS.ready).toBe('Ready for pickup');
  });
});

describe('progressIndex', () => {
  it('follows the happy path and puts cancelled off it', () => {
    expect(PROGRESS_STEPS.map(progressIndex)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(progressIndex('cancelled')).toBe(-1);
  });
});

describe('progressStates (issue #6)', () => {
  const states = (status: TicketStatus, reached: TicketStatus[]) =>
    Object.fromEntries(progressStates(status, reached).map(({ step, state }) => [step, state]));

  it('marks a skipped step as skipped, never done', () => {
    expect(states('ready', ['received', 'diagnosing', 'repairing', 'ready'])).toEqual({
      received: 'done',
      diagnosing: 'done',
      waiting_parts: 'skipped',
      repairing: 'done',
      ready: 'current',
      delivered: 'todo',
    });
  });

  it('is done for a step entered at any point, also out of order', () => {
    const result = states('repairing', ['received', 'diagnosing', 'repairing', 'waiting_parts', 'repairing']);
    expect(result.waiting_parts).toBe('done');
    expect(result.repairing).toBe('current');
  });

  it('shows steps after the current one as todo even if reached before', () => {
    expect(states('repairing', ['received', 'diagnosing', 'ready', 'repairing']).ready).toBe('todo');
  });

  it('covers the whole path for delivered tickets and nothing for cancelled ones', () => {
    expect(Object.values(states('delivered', [...PROGRESS_STEPS]))).toEqual([
      'done', 'done', 'done', 'done', 'done', 'current',
    ]);
    expect(progressStates('cancelled', ['received', 'cancelled'])).toEqual([]);
  });
});
