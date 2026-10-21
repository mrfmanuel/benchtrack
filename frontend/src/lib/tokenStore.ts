// The staff token lives in localStorage (spec §5); "Sign out" and any 401 clear it.

export const TOKEN_STORAGE_KEY = 'benchtrack.staffToken';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Storage unavailable: nothing to clear.
  }
}
