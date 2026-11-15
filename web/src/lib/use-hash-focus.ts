"use client";

import { useEffect } from "react";

/**
 * Deep links like `/requests/abc#triage`: on first mount scroll that element into view and focus it WITHOUT
 * a second scroll, then drop the hash so later re-renders/remounts (live updates) never re-trigger a jump.
 */
export function useHashFocus(id: string): void {
  useEffect(() => {
    if (typeof window === "undefined" || window.location.hash !== `#${id}`) return;
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ block: "start" });
    el.focus({ preventScroll: true });
    window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
  }, [id]);
}
