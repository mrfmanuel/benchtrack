import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../api/client';

export interface ApiState<T> {
  /** Last successful result (kept while a newer request is loading). */
  data: T | null;
  /** Error of the current request, if it failed. */
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError(0, 'unexpected_error', 'Something went wrong. Please try again.');
}

interface Settled<T> {
  requestId: string | null;
  data: T | null;
  error: ApiError | null;
}

/**
 * Runs `load` on mount and whenever `key` changes (or `reload()` is called). Responses
 * that arrive after a newer request started are ignored.
 */
export function useApi<T>(load: () => Promise<T>, key: string): ApiState<T> {
  const [version, setVersion] = useState(0);
  const [settled, setSettled] = useState<Settled<T>>({ requestId: null, data: null, error: null });
  const requestId = `${key}#${version}`;
  const loadRef = useRef(load);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let current = true;
    loadRef.current().then(
      (data) => {
        if (current) setSettled({ requestId, data, error: null });
      },
      (err: unknown) => {
        if (current) setSettled((prev) => ({ requestId, data: prev.data, error: toApiError(err) }));
      },
    );
    return () => {
      current = false;
    };
  }, [requestId]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const setData = useCallback((data: T) => setSettled((prev) => ({ ...prev, data })), []);

  const loading = settled.requestId !== requestId;
  return {
    data: settled.data,
    error: loading ? null : settled.error,
    loading,
    reload,
    setData,
  };
}
