import { Link } from 'react-router';

import { EmptyState, PageHeader } from '../components/ui';

export function NotFoundPage({ what = 'Page' }: { what?: string }) {
  return (
    <>
      <PageHeader title={`${what} not found`} />
      <EmptyState>
        It may have been mistyped. <Link to="/dashboard">Go to the dashboard</Link>.
      </EmptyState>
    </>
  );
}
