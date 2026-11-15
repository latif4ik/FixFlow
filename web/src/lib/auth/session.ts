import type { MembershipOut, UserBrief } from "@/lib/api/types";

export interface StoredSession {
  token: string;
  expiresAt: string;
  user: UserBrief;
  memberships: MembershipOut[];
  /** Selected organization id (null until chosen when several memberships exist). */
  orgId: string | null;
}

const KEY = "fixflow.session";

/** sessionStorage only (cleared with the tab); every access is guarded. */
export function loadSession(): StoredSession | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as StoredSession;
    if (!s.token || !Array.isArray(s.memberships)) return null;
    if (s.expiresAt && Date.parse(s.expiresAt) <= Date.now()) return null;
    return s;
  } catch {
    return null;
  }
}

export function saveSession(s: StoredSession): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

export function clearStoredSession(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/** Only same-origin relative paths are accepted as post-login targets (no open redirect). */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return null;
  return next;
}
