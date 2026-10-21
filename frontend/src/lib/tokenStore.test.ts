import { describe, expect, it } from 'vitest';

import { TOKEN_STORAGE_KEY, clearToken, getToken, setToken } from './tokenStore';

describe('tokenStore', () => {
  it('stores, reads and clears the token in localStorage', () => {
    expect(getToken()).toBeNull();
    setToken('fictional-staff-token-1234');
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('fictional-staff-token-1234');
    expect(getToken()).toBe('fictional-staff-token-1234');
    clearToken();
    expect(getToken()).toBeNull();
  });
});
