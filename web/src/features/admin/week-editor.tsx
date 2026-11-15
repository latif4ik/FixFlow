"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button, IconButton, Input } from "@/components/ui";
import { WEEKDAYS } from "./shared";

export interface DayInterval {
  weekday: number;
  start: string; // "HH:MM"
  end: string; // "HH:MM"
}

/** Returns an error message per weekday (index 0 = Monday). Missing key = valid. */
export function validateIntervals(list: DayInterval[]): Record<number, string> {
  const errors: Record<number, string> = {};
  for (let d = 0; d < 7; d++) {
    const day = list.filter((i) => i.weekday === d);
    if (day.some((i) => !i.start || !i.end)) {
      errors[d] = "Enter both a start and an end time.";
      continue;
    }
    if (day.some((i) => i.end <= i.start)) {
      errors[d] = "Each interval must end after it starts.";
      continue;
    }
    const sorted = [...day].sort((a, b) => a.start.localeCompare(b.start));
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i]!.start < sorted[i - 1]!.end) {
        errors[d] = `Intervals overlap (${sorted[i - 1]!.start}-${sorted[i - 1]!.end} and ${sorted[i]!.start}-${sorted[i]!.end}).`;
        break;
      }
    }
  }
  return errors;
}

/**
 * Weekly intervals editor shared by business hours and technician availability.
 * Holds a local DRAFT (this is form state, not server state); remount with a new `key` to reset it from fresh server data.
 * A weekday without intervals means closed / unavailable.
 */
export function WeekEditor({
  initial,
  onSave,
  saving,
  saveLabel = "Save",
  idPrefix,
  closedLabel = "Closed",
}: {
  initial: DayInterval[];
  onSave: (intervals: DayInterval[]) => void | Promise<unknown>;
  saving?: boolean;
  saveLabel?: string;
  idPrefix: string;
  closedLabel?: string;
}) {
  const [draft, setDraft] = useState<DayInterval[]>(initial);
  const errors = validateIntervals(draft);
  const hasErrors = Object.keys(errors).length > 0;

  const update = (idx: number, patch: Partial<DayInterval>) => setDraft((d) => d.map((x, i) => (i === idx ? { ...x, ...patch } : x)));

  return (
    <form
      aria-label={`${idPrefix} weekly editor`}
      onSubmit={(e) => {
        e.preventDefault();
        if (hasErrors || saving) return;
        void onSave(draft);
      }}
      className="flex flex-col gap-1"
    >
      {WEEKDAYS.map((name, d) => {
        const rows = draft.map((x, idx) => ({ x, idx })).filter((r) => r.x.weekday === d);
        const err = errors[d];
        return (
          <div key={name} className="flex flex-col gap-2 border-t border-border py-3 first:border-t-0 sm:flex-row sm:items-start">
            <div className="w-28 shrink-0 pt-2 text-sm font-semibold text-ink">{name}</div>
            <div className="flex flex-1 flex-col gap-2">
              {rows.length === 0 && <p className="pt-2 text-sm text-muted">{closedLabel}</p>}
              {rows.map(({ x, idx }, n) => (
                <div key={idx} className="flex flex-wrap items-center gap-2">
                  <Input
                    type="time"
                    aria-label={`${name} interval ${n + 1} start`}
                    value={x.start}
                    onChange={(e) => update(idx, { start: e.target.value })}
                    invalid={Boolean(err)}
                    className="w-32"
                  />
                  <span aria-hidden className="text-muted">
                    to
                  </span>
                  <Input type="time" aria-label={`${name} interval ${n + 1} end`} value={x.end} onChange={(e) => update(idx, { end: e.target.value })} invalid={Boolean(err)} className="w-32" />
                  <IconButton
                    aria-label={`Remove ${name} interval ${n + 1}`}
                    variant="ghost"
                    icon={<Trash2 className="size-4" aria-hidden />}
                    onClick={() => setDraft((dr) => dr.filter((_, i) => i !== idx))}
                  />
                </div>
              ))}
              {err && (
                <p role="alert" className="text-[13px] font-semibold text-danger-dark">
                  {name}: {err}
                </p>
              )}
              <div>
                <Button size="sm" variant="secondary" onClick={() => setDraft((dr) => [...dr, { weekday: d, start: "09:00", end: "18:00" }])}>
                  <Plus className="size-4" aria-hidden /> Add interval <span className="sr-only">on {name}</span>
                </Button>
              </div>
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-3 border-t border-border pt-4">
        <Button type="submit" loading={saving}>
          {saveLabel}
        </Button>
        {hasErrors && <p className="text-[13px] text-danger-dark">Fix the highlighted days before saving.</p>}
      </div>
    </form>
  );
}
