import { useEffect } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router';

import { EXPIRED_TOKEN_MESSAGE, setUnauthorizedHandler } from './api/client';
import { PublicLayout } from './layouts/PublicLayout';
import { RequireToken, StaffLayout } from './layouts/StaffLayout';
import { CustomerDetailPage } from './pages/CustomerDetailPage';
import { CustomersPage } from './pages/CustomersPage';
import { DashboardPage } from './pages/DashboardPage';
import { NewTicketPage } from './pages/NewTicketPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { ReceiptPage } from './pages/ReceiptPage';
import { SignInPage } from './pages/SignInPage';
import { TicketDetailPage } from './pages/TicketDetailPage';
import { TicketsPage } from './pages/TicketsPage';
import { TrackPage } from './pages/TrackPage';

/** Any 401 (token already cleared by the client) sends the user to sign-in (spec 9.25). */
function UnauthorizedRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.pathname + location.search;

  useEffect(() => {
    setUnauthorizedHandler(() =>
      navigate('/sign-in', {
        replace: true,
        state: { message: EXPIRED_TOKEN_MESSAGE, from: from === '/sign-in' ? undefined : from },
      }),
    );
  }, [navigate, from]);

  return null;
}

export function App() {
  return (
    <>
      <UnauthorizedRedirect />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/sign-in" element={<SignInPage />} />

        <Route element={<PublicLayout />}>
          <Route path="/track" element={<TrackPage />} />
          <Route path="/track/:code" element={<TrackPage />} />
        </Route>

        <Route
          path="/tickets/:id/receipt"
          element={
            <RequireToken>
              <ReceiptPage />
            </RequireToken>
          }
        />

        <Route element={<StaffLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/tickets" element={<TicketsPage />} />
          <Route path="/tickets/new" element={<NewTicketPage />} />
          <Route path="/tickets/:id" element={<TicketDetailPage />} />
          <Route path="/customers" element={<CustomersPage />} />
          <Route path="/customers/:id" element={<CustomerDetailPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </>
  );
}
