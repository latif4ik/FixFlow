/**
 * Framework-free holder for the credentials the API client needs. AuthProvider keeps it in sync.
 * Kept outside React so apiFetch can read the token without hooks. The token is never put in a URL or logged.
 */
export interface ApiAuthState {
  token: string | null;
  orgId: string | null;
}

let state: ApiAuthState = { token: null, orgId: null };
let onUnauthorized: (() => void) | null = null;

export const apiAuth = {
  get: (): ApiAuthState => state,
  set(next: Partial<ApiAuthState>) {
    state = { ...state, ...next };
  },
  clear() {
    state = { token: null, orgId: null };
  },
  setUnauthorizedHandler(fn: (() => void) | null) {
    onUnauthorized = fn;
  },
  notifyUnauthorized() {
    onUnauthorized?.();
  },
};
