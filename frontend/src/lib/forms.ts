// Form helpers: map API validation errors to fields, and turn form strings into payloads.

import type { FieldErrorDetail } from '../api/types';

export type FieldErrors = Record<string, string>;

/**
 * Split `validation_error` details into messages for known form fields and the rest
 * (e.g. body-level errors), which the form shows in its banner.
 */
export function splitFieldErrors(
  details: FieldErrorDetail[],
  knownFields: readonly string[],
): { fields: FieldErrors; other: string[] } {
  const fields: FieldErrors = {};
  const other: string[] = [];
  for (const { field, message } of details) {
    if (knownFields.includes(field)) {
      fields[field] = fields[field] ? `${fields[field]} ${message}` : message;
    } else {
      other.push(message);
    }
  }
  return { fields, other };
}

/** Trimmed text, or `null` when blank (optional fields are nullable in the API). */
export function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

export const INVALID_COST_MESSAGE = 'Enter an amount in colones, e.g. 45000.50.';

/**
 * Cost input → number for the API. Blank → `null`; thousands separators are allowed.
 * Range (0–10,000,000) is left to the server so its message is shown.
 */
export function parseCost(value: string): { value: number | null } | { error: string } {
  const trimmed = value.trim().replace(/[,\s]/g, '').replace(/^₡/, '');
  if (trimmed === '') return { value: null };
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return { error: INVALID_COST_MESSAGE };
  return { value: Number(trimmed) };
}

/**
 * Only the fields that differ from `original` (PATCH sends changes only).
 */
export function changedFields<T extends object>(original: T, edited: Partial<T>): Partial<T> {
  const changes: Partial<T> = {};
  for (const key of Object.keys(edited) as (keyof T)[]) {
    if (edited[key] !== original[key]) changes[key] = edited[key];
  }
  return changes;
}
