"use client";

import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
const TICK = 15_000;
const snap = () => Math.floor(Date.now() / TICK) * TICK;

function subscribe(fn: () => void) {
  listeners.add(fn);
  if (!timer) timer = setInterval(() => listeners.forEach((l) => l()), TICK);
  return () => {
    listeners.delete(fn);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** Current time in ms, refreshed every 15 s (0 during SSR). Use instead of Date.now() in render. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, snap, () => 0);
}
