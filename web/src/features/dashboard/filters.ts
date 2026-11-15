"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

export interface ReportFilters {
  from?: string;
  to?: string;
  category_id?: string;
  technician_id?: string;
}

const KEYS = ["from", "to", "category_id", "technician_id"] as const;

/** Report filters live in the URL query string (shareable, survives reload). Values go straight to the API. */
export function useReportFilters(): { filters: ReportFilters; setFilter: (key: keyof ReportFilters, value: string) => void; clear: () => void } {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const filters: ReportFilters = {};
  for (const k of KEYS) {
    const v = sp.get(k);
    if (v) filters[k] = v;
  }
  const push = useCallback(
    (next: ReportFilters) => {
      const q = new URLSearchParams();
      for (const k of KEYS) if (next[k]) q.set(k, next[k]!);
      const s = q.toString();
      router.replace(s ? `${pathname}?${s}` : pathname);
    },
    [router, pathname],
  );
  const current = JSON.stringify(filters);
  const setFilter = useCallback(
    (key: keyof ReportFilters, value: string) => {
      const next: ReportFilters = { ...(JSON.parse(current) as ReportFilters) };
      if (value) next[key] = value;
      else delete next[key];
      push(next);
    },
    [current, push],
  );
  const clear = useCallback(() => push({}), [push]);
  return { filters, setFilter, clear };
}
