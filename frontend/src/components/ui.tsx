// Small presentational building blocks shared by the pages.

import type { ReactNode } from 'react';

import type { ApiError } from '../api/client';
import type { TicketStatus } from '../api/types';
import { describeError } from '../lib/errors';
import { STATUS_TONES, statusLabel } from '../lib/statuses';

export function StatusBadge({ status }: { status: TicketStatus }) {
  return <span className={`badge badge--${STATUS_TONES[status]}`}>{statusLabel(status)}</span>;
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </p>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

interface BannerProps {
  tone?: 'error' | 'warning' | 'info' | 'success';
  title?: string;
  children: ReactNode;
}

export function Banner({ tone = 'error', title, children }: BannerProps) {
  return (
    <div className={`banner banner--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {title && <strong className="banner__title">{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

/** Banner for a failed request (409 conflicts, network errors, ...). */
export function ErrorBanner({
  error,
  title,
  children,
}: {
  error: ApiError | null;
  title?: string;
  children?: ReactNode;
}) {
  if (!error) return null;
  return (
    <Banner tone="error" title={title}>
      <p>{describeError(error)}</p>
      {children}
    </Banner>
  );
}

export function PageHeader({ title, actions, children }: { title: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {children}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </div>
  );
}

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}

export function Pagination({ total, limit, offset, onChange }: PaginationProps) {
  if (total <= limit && offset === 0) return null;
  const first = total === 0 ? 0 : offset + 1;
  const last = Math.min(offset + limit, total);
  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="button button--secondary"
        onClick={() => onChange(Math.max(0, offset - limit))}
        disabled={offset === 0}
      >
        Previous
      </button>
      <span aria-live="polite">
        {first}–{last} of {total}
      </span>
      <button
        type="button"
        className="button button--secondary"
        onClick={() => onChange(offset + limit)}
        disabled={offset + limit >= total}
      >
        Next
      </button>
    </nav>
  );
}
