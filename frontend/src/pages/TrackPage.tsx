import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router';

import { api } from '../api/client';
import { ProgressIndicator, PublicTimeline } from '../components/Timeline';
import { Banner, Loading, StatusBadge } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { retryMessage } from '../lib/errors';
import { formatDateTime, formatDevice } from '../lib/format';
import { STATUS_DESCRIPTIONS } from '../lib/statuses';
import { normalizeTrackingCode } from '../lib/trackingCode';

/** Public tracking (spec F4, 9.23): `/track` form, `/track/:code` pre-filled auto-lookup. */
export function TrackPage() {
  const navigate = useNavigate();
  const raw = useParams().code ?? '';
  const code = raw ? normalizeTrackingCode(raw) : null;
  const canonical = code !== null && code === raw;
  const [input, setInput] = useState(code ?? raw);
  const [inputError, setInputError] = useState<string | null>(null);

  // Follow the URL when it changes (back/forward, new lookup): adjust state during render.
  const [shownRaw, setShownRaw] = useState(raw);
  if (raw !== shownRaw) {
    setShownRaw(raw);
    setInput(code ?? raw);
    setInputError(null);
  }

  // `/track/bt-7k3qx` → `/track/BT-7K3QX` before looking it up.
  useEffect(() => {
    if (code && !canonical) navigate(`/track/${code}`, { replace: true });
  }, [code, canonical, navigate]);

  const lookup = useApi(
    () => (canonical && code ? api.trackTicket(code) : Promise.resolve(null)),
    canonical && code ? code : '',
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    const normalized = normalizeTrackingCode(input);
    if (!normalized) {
      setInputError('Tracking codes look like BT-7K3QX: “BT-” followed by 5 letters or digits.');
      return;
    }
    setInputError(null);
    if (normalized === code) lookup.reload();
    else navigate(`/track/${normalized}`);
  }

  const result = canonical ? lookup.data : null;
  const error = canonical ? lookup.error : null;

  return (
    <div className="track">
      <h1>Track your repair</h1>
      <p className="muted">Enter the tracking code printed on your receipt.</p>

      <form className="track__form" onSubmit={submit} noValidate role="search" aria-label="Track a repair">
        <label htmlFor="tracking-code">Tracking code</label>
        <div className="track__row">
          <input
            id="tracking-code"
            className="code"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={20}
            placeholder="BT-7K3QX"
            value={input}
            aria-invalid={inputError ? true : undefined}
            aria-describedby={inputError ? 'tracking-code-error' : undefined}
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" className="button">
            Track
          </button>
        </div>
        {inputError && (
          <p className="field__error" id="tracking-code-error">
            {inputError}
          </p>
        )}
      </form>

      {raw && code === null && <NotFound code={raw} />}
      {canonical && lookup.loading && <Loading label="Looking up your repair…" />}
      {error?.status === 404 && <NotFound code={code ?? raw} />}
      {error?.status === 429 && (
        <Banner tone="warning" title="Too many lookups">
          You have checked several codes in a short time. {retryMessage(error.retryAfter)}
        </Banner>
      )}
      {error && error.status !== 404 && error.status !== 429 && (
        <Banner tone="error" title="Tracking is unavailable right now">
          Please try again in a few minutes.
        </Banner>
      )}

      {result && !lookup.loading && !error && (
        <section className="card track__result" aria-labelledby="track-result-title">
          <div className="track__summary">
            <div>
              <h2 id="track-result-title" className="code">
                {result.tracking_code}
              </h2>
              <p>{formatDevice(result)}</p>
            </div>
            <StatusBadge status={result.status} />
          </div>
          <p className="track__description">{STATUS_DESCRIPTIONS[result.status]}</p>
          <ProgressIndicator status={result.status} />
          <p className="muted small">
            Last update: <time dateTime={result.last_status_change_at}>{formatDateTime(result.last_status_change_at)}</time>
          </p>
          <h3>History</h3>
          <PublicTimeline timeline={result.timeline} />
        </section>
      )}
    </div>
  );
}

function NotFound({ code }: { code: string }) {
  return (
    <Banner tone="warning" title="Repair not found">
      We couldn’t find a repair with the code <strong className="code">{code}</strong>. Check the code on your receipt
      and try again.
    </Banner>
  );
}
