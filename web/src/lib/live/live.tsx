"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { API_PREFIX, API_URL, api, isApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";
import { qk, requestChangedPrefixes } from "@/lib/query/keys";

export type LiveStatus = "live" | "reconnecting" | "offline";

const LiveContext = createContext<LiveStatus>("offline");
export const useLiveStatus = (): LiveStatus => useContext(LiveContext);

/** Backoff for reconnects: 1s doubling up to 30s. */
export function backoffDelay(attempt: number): number {
  return Math.min(30_000, 1000 * 2 ** attempt);
}

/**
 * Events only trigger invalidation (never carry data into the cache).
 * request.changed {request_id} -> requests + detail + dashboards/reports/schedule/estimates prefixes
 * notification.created        -> notifications
 * resync / ready (re)connect  -> everything for the org
 */
export function handleLiveEvent(qc: QueryClient, orgId: string, type: string, raw: string | null): void {
  let data: { request_id?: string } = {};
  try {
    data = raw ? (JSON.parse(raw) as typeof data) : {};
  } catch {
    /* ignore malformed payload */
  }
  if (type === "request.changed") {
    for (const queryKey of requestChangedPrefixes(orgId, data.request_id)) void qc.invalidateQueries({ queryKey });
    // a changed request can change the overdue badge too (covered by dashboard prefix)
  } else if (type === "notification.created") {
    void qc.invalidateQueries({ queryKey: qk.notifications.all(orgId) });
  } else if (type === "resync" || type === "ready") {
    void qc.invalidateQueries({ queryKey: qk.all(orgId) });
  }
}

const EVENT_TYPES = ["ready", "request.changed", "notification.created", "resync", "closed"] as const;

export function LiveUpdatesProvider({ children }: { children: ReactNode }) {
  const { orgId, status, markExpired } = useAuth();
  const qc = useQueryClient();
  const [live, setLive] = useState<{ orgId: string; status: LiveStatus } | null>(null);

  useEffect(() => {
    if (!orgId || status !== "authenticated" || typeof EventSource === "undefined") return;
    let stopped = false;
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let connectedBefore = false;

    const set = (s: LiveStatus) => !stopped && setLive({ orgId, status: s });

    const schedule = () => {
      if (stopped) return;
      set(typeof navigator !== "undefined" && navigator.onLine === false ? "offline" : "reconnecting");
      timer = setTimeout(connect, backoffDelay(attempt++));
    };

    const connect = async () => {
      if (stopped) return;
      try {
        // A NEW ticket for every connection (tickets are single-use and short-lived).
        const { ticket } = await api.post<{ ticket: string; expires_at: string }>("/stream/ticket", undefined, { orgId });
        if (stopped) return;
        es = new EventSource(`${API_URL}${API_PREFIX}/stream?ticket=${encodeURIComponent(ticket)}`);
        for (const t of EVENT_TYPES) {
          es.addEventListener(t, (ev) => {
            const msg = ev as MessageEvent<string>;
            if (t === "ready") {
              attempt = 0;
              set("live");
              // Anything may have changed while we were disconnected.
              if (connectedBefore) handleLiveEvent(qc, orgId, "resync", null);
              connectedBefore = true;
              return;
            }
            if (t === "closed") {
              es?.close();
              schedule();
              return;
            }
            handleLiveEvent(qc, orgId, t, msg.data);
          });
        }
        es.onerror = () => {
          es?.close();
          es = null;
          schedule();
        };
      } catch (e) {
        if (isApiError(e) && e.status === 401) {
          markExpired();
          return;
        }
        schedule();
      }
    };

    const onOnline = () => {
      if (timer) clearTimeout(timer);
      attempt = 0;
      void connect();
    };
    const onOffline = () => set("offline");
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    void connect();

    return () => {
      stopped = true; // closes SSE on org switch / logout / unmount
      if (timer) clearTimeout(timer);
      es?.close();
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [orgId, status, qc, markExpired]);

  const value = useMemo<LiveStatus>(() => (live && live.orgId === orgId ? live.status : "reconnecting"), [live, orgId]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}
