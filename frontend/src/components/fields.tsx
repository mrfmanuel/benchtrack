// Labelled form controls that show a server validation message under the input.

import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

interface FieldShellProps {
  id: string;
  label: string;
  error?: string;
  hint?: ReactNode;
  required?: boolean;
  children: ReactNode;
}

function FieldShell({ id, label, error, hint, required, children }: FieldShellProps) {
  return (
    <div className={`field${error ? ' field--invalid' : ''}`}>
      <label htmlFor={id}>
        {label}
        {required ? (
          <span className="field__required" aria-hidden="true">
            {' '}
            *
          </span>
        ) : (
          <span className="field__optional"> (optional)</span>
        )}
      </label>
      {children}
      {hint && !error && (
        <p className="field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field__error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}

function describedBy(id: string, error?: string, hint?: ReactNode) {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

type Common = { id: string; label: string; error?: string; hint?: ReactNode };

export function TextField({ id, label, error, hint, required, ...input }: Common & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} required={required}>
      <input
        id={id}
        name={id}
        aria-required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, error, hint)}
        {...input}
      />
    </FieldShell>
  );
}

export function TextAreaField({
  id,
  label,
  error,
  hint,
  required,
  ...input
}: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} required={required}>
      <textarea
        id={id}
        name={id}
        rows={3}
        aria-required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, error, hint)}
        {...input}
      />
    </FieldShell>
  );
}

export function SelectField({
  id,
  label,
  error,
  hint,
  required,
  children,
  ...input
}: Common & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} required={required}>
      <select
        id={id}
        name={id}
        aria-required={required || undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, error, hint)}
        {...input}
      >
        {children}
      </select>
    </FieldShell>
  );
}
