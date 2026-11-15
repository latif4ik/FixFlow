"use client";

import { AlertTriangle, CalendarClock, Check, RefreshCw, UserMinus, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, ConfirmDialog, EmptyState, ErrorState, FormField, InlineNote, Input, LoadingState, Panel, DateTime } from "@/components/ui";
import { isApiError } from "@/lib/api/client";
import type { ApiError } from "@/lib/api/client";
import type { Page, Schemas } from "@/lib/api/types";
import { formatDateTime, formatDuration } from "@/lib/format";
import { useApiMutation, useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";
import { useNow } from "@/lib/use-now";
import type { RequestActionProps } from "@/features/request-actions/types";
import { localDate, localTime, reasonMessages, zonedToUtcIso } from "../lib/tz";

type Suggestions = Schemas["SuggestionsOut"];
type Suggestion = Schemas["SuggestionOut"];
type Candidate = Schemas["CandidateOut"];
type AssignmentOut = Schemas["AssignmentOut"];
type CategoryOut = Schemas["CategoryOut"];

interface AssignVars {
  technician_membership_id: string;
  start_at: string;
  end_at: string;
}

/** Shared by Assign (POST) and Reschedule (PUT). A 409/422 means the slot is no longer available. */
function useAssignMutation(ctx: RequestActionProps["ctx"], mode: "assign" | "reschedule", onStale: (message: string, reasons: string[]) => void, onDone: () => void) {
  return useApiMutation<unknown, AssignVars>({
    request: (v) => ({ method: mode === "assign" ? "POST" : "PUT", path: `/requests/${ctx.requestId}/assignment`, body: v }),
    idempotent: true,
    errorMessage: false,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.all(o), qk.schedule.all(o)],
    successMessage: mode === "assign" ? "Technician assigned." : "Appointment rescheduled.",
    onSuccess: onDone,
    onError: (e: ApiError) => {
      if (isApiError(e) && (e.status === 409 || e.status === 422)) {
        onStale(e.message, reasonMessages(e.details));
      } else {
        onStale(e.message, []);
      }
    },
  });
}

export function slaText(s: Suggestion, tz: string): { breach: boolean; text: string } {
  const due = s.sla.due_at;
  if (!due) return { breach: false, text: "No SLA due time." };
  const dueTxt = formatDateTime(due, tz, "short");
  const diffMin = Math.round((new Date(due).getTime() - new Date(s.end_at).getTime()) / 60000);
  if (s.sla.slot_ends_after_due) {
    return { breach: true, text: `Slot ends ${formatDuration(Math.abs(diffMin))} after the SLA due time (${dueTxt}).` };
  }
  return { breach: false, text: `Slot ends ${formatDuration(Math.max(0, diffMin))} before the SLA due time (${dueTxt}).` };
}

function windowText(startIso: string, endIso: string, tz: string): string {
  const day = formatDateTime(startIso, tz, "short");
  return `${day} - ${formatDateTime(endIso, tz, "time")}`;
}

function SlotCard({ s, tz, pending, disabled, onAssign, verb }: { s: Suggestion; tz: string; pending: boolean; disabled: boolean; onAssign: () => void; verb: string }) {
  const sla = slaText(s, tz);
  const label = `${verb} ${s.technician.name}, ${windowText(s.start_at, s.end_at, tz)}`;
  return (
    <li className="flex flex-col gap-2.5 rounded-lg border border-border bg-surface p-4">
      <span className="text-[13px] font-semibold text-muted">{s.technician.name}</span>
      <span className="font-heading text-lg font-extrabold leading-tight">{windowText(s.start_at, s.end_at, tz)}</span>
      {sla.breach ? (
        <Badge tone="warning" icon={AlertTriangle} className="h-auto items-start whitespace-normal">
          Breaches SLA. {sla.text}
        </Badge>
      ) : (
        <Badge tone="success" icon={Check} className="h-auto items-start whitespace-normal">
          Within SLA. {sla.text}
        </Badge>
      )}
      <span className="text-xs text-muted">
        {s.reason} · {formatDuration(s.workload_minutes_next_7_days)} booked in the next 7 days
      </span>
      <Button className="mt-auto" aria-label={label} onClick={onAssign} loading={pending} disabled={disabled}>
        {verb}
      </Button>
    </li>
  );
}

function CandidateRow({ c, required, onAssign, pending, disabled, verb }: { c: Candidate; required: string[]; onAssign: () => void; pending: boolean; disabled: boolean; verb: string }) {
  const have = required.filter((r) => c.skills.some((s) => s.toLowerCase() === r.toLowerCase())).length;
  const missing = c.reasons.find((r) => r.code === "missing_skills");
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border py-3 first:border-t-0">
      <span className="min-w-36 flex-[0_0_auto] font-semibold">{c.name}</span>
      <span className="flex min-w-52 flex-1 flex-col gap-0.5 text-[13px]">
        {required.length > 0 && (
          <span className={`flex items-center gap-1.5 font-semibold ${have === required.length ? "text-primary-dark" : "text-danger-dark"}`}>
            {have === required.length ? <Check className="size-3.5" aria-hidden /> : <X className="size-3.5" aria-hidden />}
            Skills {have} of {required.length}
          </span>
        )}
        {c.reasons.length === 0 ? (
          <span className="text-muted">Free in this window</span>
        ) : (
          c.reasons.map((r, i) => (
            <span key={`${r.code}-${i}`} className="flex items-center gap-1.5 text-danger-dark">
              <X className="size-3.5 shrink-0" aria-hidden />
              <span>{reasonLine(r, missing === r)}</span>
            </span>
          ))
        )}
      </span>
      <span className="text-[13px] text-muted">
        {c.workload.active_assignments} active job{c.workload.active_assignments === 1 ? "" : "s"} · {formatDuration(c.workload.planned_minutes_next_7_days)} next 7 days
      </span>
      {c.eligible ? (
        <Badge tone="success" icon={Check}>
          Eligible
        </Badge>
      ) : (
        <Badge tone="neutral" icon={X}>
          Not eligible
        </Badge>
      )}
      {c.eligible && (
        <Button size="sm" aria-label={`${verb} ${c.name} to this window`} onClick={onAssign} loading={pending} disabled={disabled}>
          {verb}
        </Button>
      )}
    </li>
  );
}

function reasonLine(r: Candidate["reasons"][number], _isMissing: boolean): string {
  const msg = String(r.message ?? r.code ?? "Not available");
  if (r.code === "overlap") {
    const list = ((r.details as { assignments?: { display_id: string }[] } | undefined)?.assignments ?? []).map((a) => a.display_id);
    if (list.length) return `Overlaps ${list.join(", ")}`;
  }
  return msg;
}

/** Day window + business-hours-agnostic input group, in the ORG timezone. */
function WindowFields({ date, from, to, onChange, labels }: { date: string; from: string; to: string; onChange: (v: { date?: string; from?: string; to?: string }) => void; labels: [string, string] }) {
  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-3">
      <FormField label="Date" className="w-44">
        <Input type="date" value={date} onChange={(e) => onChange({ date: e.target.value })} />
      </FormField>
      <FormField label={labels[0]} className="w-36">
        <Input type="time" value={from} onChange={(e) => onChange({ from: e.target.value })} />
      </FormField>
      <FormField label={labels[1]} className="w-36">
        <Input type="time" value={to} onChange={(e) => onChange({ to: e.target.value })} />
      </FormField>
    </div>
  );
}

function Scheduler({ ctx, mode, onDone }: RequestActionProps & { mode: "assign" | "reschedule"; onDone: () => void }) {
  const { detail, timezone: tz, requestId } = ctx;
  const now = useNow();
  const verb = mode === "assign" ? "Assign" : "Reschedule";
  const preferred = detail.preferred_window_start;
  const defaults = useMemo(
    () => ({
      date: preferred ? localDate(preferred, tz) : now > 0 ? localDate(now, tz) : "",
      from: preferred ? localTime(preferred, tz) : "09:00",
      to: "18:00",
      manTo: detail.preferred_window_end ? localTime(detail.preferred_window_end, tz) : "10:30",
    }),
    [preferred, detail.preferred_window_end, now, tz],
  );
  const [view, setView] = useState<"suggest" | "manual">("suggest");
  const [win, setWin] = useState<{ date?: string; from?: string; to?: string }>({});
  const [man, setMan] = useState<{ date?: string; from?: string; to?: string }>({});
  const [requested, setRequested] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [stale, setStale] = useState<{ message: string; reasons: string[] } | null>(null);
  const winV = { date: win.date ?? defaults.date, from: win.from ?? defaults.from, to: win.to ?? defaults.to };
  const manV = { date: man.date ?? defaults.date, from: man.from ?? defaults.from, to: man.to ?? defaults.manTo };

  const cats = useApiQuery<Page<CategoryOut>>({ queryKey: (o) => qk.categories.list(o, { page_size: 100 }), path: "/categories", query: { page_size: 100 }, staleTime: 60_000 });
  const category = cats.data?.items.find((c) => c.id === detail.category.id);
  const required = (category?.required_skills ?? []).map((s) => s.name);
  const durationNote = category ? `${category.name} jobs default to ${formatDuration(category.default_duration_minutes)}.` : null;

  const winStart = winV.date && winV.from ? zonedToUtcIso(winV.date, winV.from, tz) : null;
  const winEnd = winV.date && winV.to ? zonedToUtcIso(winV.date, winV.to, tz) : null;
  const winValid = Boolean(winStart && winEnd && Date.parse(winEnd) > Date.parse(winStart));
  const horizon = winEnd && now > 0 ? Math.min(31, Math.max(1, Math.ceil((new Date(winEnd).getTime() - now) / 86_400_000) + 1)) : 14;
  const sugParams = { horizon_days: horizon, limit: 20 };
  const sug = useApiQuery<Suggestions>({
    queryKey: (o) => qk.requests.suggestions(o, requestId, sugParams),
    path: `/requests/${requestId}/suggestions`,
    query: sugParams,
    enabled: requested && view === "suggest",
    staleTime: 0,
  });

  const manStart = manV.date && manV.from ? zonedToUtcIso(manV.date, manV.from, tz) : null;
  const manEnd = manV.date && manV.to ? zonedToUtcIso(manV.date, manV.to, tz) : null;
  const manValid = Boolean(manStart && manEnd && Date.parse(manEnd) > Date.parse(manStart));
  const candParams = { start_at: manStart ?? undefined, end_at: manEnd ?? undefined };
  const cand = useApiQuery<Candidate[]>({
    queryKey: (o) => qk.requests.candidates(o, requestId, candParams),
    path: `/requests/${requestId}/candidates`,
    query: candParams,
    enabled: view === "manual" && manValid,
    staleTime: 0,
  });

  const assign = useAssignMutation(
    ctx,
    mode,
    (message, reasons) => setStale({ message, reasons }),
    () => {
      setStale(null);
      onDone();
    },
  );

  const allSlots = sug.data?.suggestions ?? [];
  const slots = showAll || !winStart || !winEnd || !winValid ? allSlots : allSlots.filter((s) => Date.parse(s.start_at) >= Date.parse(winStart) && Date.parse(s.end_at) <= Date.parse(winEnd));
  const hiddenCount = (sug.data?.suggestions.length ?? 0) - slots.length;

  function refresh() {
    setStale(null);
    void sug.refetch();
    void cand.refetch();
  }

  return (
    <div className="flex flex-col gap-5">
      {stale && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning-tint px-4 py-3.5 text-warning-dark">
          <span className="flex min-w-0 flex-col gap-1 font-semibold">
            <span className="flex items-center gap-2">
              <AlertTriangle className="size-[18px] shrink-0" aria-hidden />
              Slot just taken — refresh suggestions
            </span>
            <span className="text-[13px] font-normal">{[stale.message, ...stale.reasons].filter(Boolean).join(" ")}</span>
          </span>
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw className="size-4" aria-hidden /> Refresh suggestions
          </Button>
        </div>
      )}

      <div role="group" aria-label="How to choose a slot" className="inline-flex w-fit rounded-md border border-border-strong p-0.5">
        {(["suggest", "manual"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => setView(v)}
            className={`rounded-sm px-3 py-1.5 text-sm font-semibold ${view === v ? "bg-primary text-white" : "text-text hover:bg-canvas-2"}`}
          >
            {v === "suggest" ? "Smart suggestions" : "Pick manually"}
          </button>
        ))}
      </div>

      {view === "suggest" ? (
        <>
          <section aria-labelledby="win-h" className="flex flex-col gap-3">
            <h3 id="win-h" className="text-sm font-semibold">
              Time window
            </h3>
            <WindowFields date={winV.date} from={winV.from} to={winV.to} labels={["Earliest start", "Latest finish"]} onChange={(v) => setWin((w) => ({ ...w, ...v }))} />
            <p className="text-[13px] text-muted">
              {durationNote ?? ""} Times in {tz}. Suggestions are advisory: the server re-checks eligibility and conflicts when you assign.
            </p>
            <div>
              <Button
                onClick={() => {
                  setStale(null);
                  if (requested) void sug.refetch();
                  setRequested(true);
                }}
                loading={sug.isFetching}
                disabled={!winValid}
              >
                <RefreshCw className="size-4" aria-hidden /> Suggest slots
              </Button>
              {!winValid && <span className="ml-3 text-[13px] text-danger-dark">Latest finish must be after earliest start.</span>}
            </div>
          </section>

          {requested && (
            <section aria-labelledby="slots-h" className="flex flex-col gap-3">
              <h3 id="slots-h" className="text-sm font-semibold">
                Suggested slots
              </h3>
              {sug.isLoading ? (
                <LoadingState label="Finding slots" />
              ) : sug.error ? (
                <ErrorState error={sug.error} onRetry={() => void sug.refetch()} />
              ) : slots.length === 0 ? (
                <EmptyState
                  title="No slots inside this window"
                  description={
                    hiddenCount > 0
                      ? `${hiddenCount} suggestion${hiddenCount === 1 ? " exists" : "s exist"} outside the window.`
                      : `No eligible technician is free. ${sug.data?.unskilled_technicians ?? 0} technician(s) lack the required skills; try Pick manually to see why.`
                  }
                  action={
                    hiddenCount > 0 ? (
                      <Button variant="secondary" onClick={() => setShowAll(true)}>
                        Show all suggestions
                      </Button>
                    ) : undefined
                  }
                />
              ) : (
                <>
                  <ul className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr))]">
                    {slots.map((s) => (
                      <SlotCard
                        key={`${s.technician.membership_id}-${s.start_at}`}
                        s={s}
                        tz={tz}
                        verb={verb}
                        pending={assign.isPending && assign.variables?.start_at === s.start_at && assign.variables?.technician_membership_id === s.technician.membership_id}
                        disabled={assign.isPending}
                        onAssign={() => assign.mutate({ technician_membership_id: s.technician.membership_id, start_at: s.start_at, end_at: s.end_at })}
                      />
                    ))}
                  </ul>
                  {showAll && hiddenCount === 0 && (
                    <button type="button" className="w-fit text-[13px] font-semibold text-primary-dark underline" onClick={() => setShowAll(false)}>
                      Only show slots inside my window
                    </button>
                  )}
                </>
              )}
              {sug.data && sug.data.skipped.length > 0 && (
                <p className="text-[13px] text-muted">
                  Skipped: {sug.data.skipped.map((k) => `${k.technician.name} (${k.reason_codes.join(", ").replaceAll("_", " ")})`).join("; ")}
                </p>
              )}
            </section>
          )}
        </>
      ) : (
        <section aria-labelledby="man-h" className="flex flex-col gap-3">
          <h3 id="man-h" className="text-sm font-semibold">
            Appointment window
          </h3>
          <WindowFields date={manV.date} from={manV.from} to={manV.to} labels={["Start", "End"]} onChange={(v) => setMan((w) => ({ ...w, ...v }))} />
          <p className="text-[13px] text-muted">Times in {tz}. Appointments must be at least 30 minutes.</p>
          <h3 className="mt-2 text-sm font-semibold">Technicians{category ? ` for ${category.name}` : ""}</h3>
          {!manValid ? (
            <InlineNote>Enter a start and an end time to see who can take this window.</InlineNote>
          ) : cand.isLoading ? (
            <LoadingState label="Checking technicians" />
          ) : cand.error ? (
            <ErrorState error={cand.error} onRetry={() => void cand.refetch()} />
          ) : (
            <ul aria-label="Technician eligibility" className="flex flex-col">
              {(cand.data ?? []).map((c) => (
                <CandidateRow
                  key={c.membership_id}
                  c={c}
                  required={required}
                  verb={verb}
                  pending={assign.isPending && assign.variables?.technician_membership_id === c.membership_id}
                  disabled={assign.isPending}
                  onAssign={() => assign.mutate({ technician_membership_id: c.membership_id, start_at: manStart!, end_at: manEnd! })}
                />
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function History({ ctx }: RequestActionProps) {
  const q = useApiQuery<AssignmentOut[]>({
    queryKey: (o) => qk.custom(o, "requests", "detail", ctx.requestId, "assignments"),
    path: `/requests/${ctx.requestId}/assignments`,
  });
  if (q.isLoading) return null;
  if (q.error || !q.data || q.data.length === 0) return null;
  return (
    <section aria-labelledby="hist-h" className="flex flex-col gap-2">
      <h3 id="hist-h" className="text-sm font-semibold">
        Assignment history
      </h3>
      <ul className="flex flex-col text-[13px]">
        {q.data.map((a) => (
          <li key={a.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-border py-2 first:border-t-0">
            <span className="font-semibold text-ink">{a.technician.name}</span>
            <span className="text-muted">{windowText(a.start_at, a.end_at, ctx.timezone)}</span>
            <Badge tone={a.active ? "success" : "neutral"}>{a.active ? "Current" : a.status.charAt(0) + a.status.slice(1).toLowerCase()}</Badge>
            {a.released_reason && (
              <span className="text-muted">
                Released{a.released_by ? ` by ${a.released_by.name}` : ""}: &ldquo;{a.released_reason}&rdquo;
                {a.released_at && (
                  <>
                    {" "}
                    (<DateTime value={a.released_at} style="short" />)
                  </>
                )}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AssignmentPanel({ ctx }: RequestActionProps) {
  const { detail } = ctx;
  const assignment = detail.assignment && detail.assignment.status === "ACTIVE" ? detail.assignment : null;
  const canSchedule = ctx.allowed.has("assign");
  const canReschedule = ctx.allowed.has("reschedule");
  const canUnassign = ctx.allowed.has("unassign");
  const [rescheduling, setRescheduling] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash === "#assign" && ref.current) {
      ref.current.scrollIntoView({ block: "start" });
      ref.current.focus();
    }
  }, []);

  const unassign = useApiMutation<unknown, { reason: string }>({
    request: (v) => ({ path: `/requests/${ctx.requestId}/assignment/unassign`, body: v }),
    idempotent: true,
    invalidate: (o) => [qk.requests.detail(o, ctx.requestId), qk.requests.all(o), qk.schedule.all(o)],
    successMessage: "Technician unassigned. The request is back to Triaged.",
  });

  return (
    <Panel title="Assignment" className="scroll-mt-20" bodyClassName="flex flex-col gap-5">
      <section id="assign" ref={ref} tabIndex={-1} aria-label="Assignment" className="flex flex-col gap-5 outline-none">
        {assignment ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-canvas p-4">
            <div className="flex flex-col gap-0.5">
              <span className="text-[13px] text-muted">Assigned technician</span>
              <span className="font-semibold text-ink">{assignment.technician.name}</span>
              <span className="text-sm text-text">{windowText(assignment.start_at, assignment.end_at, ctx.timezone)}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {canReschedule && (
                <Button variant="secondary" onClick={() => setRescheduling((r) => !r)} aria-expanded={rescheduling}>
                  <CalendarClock className="size-4" aria-hidden /> {rescheduling ? "Close reschedule" : "Reschedule"}
                </Button>
              )}
              {canUnassign && (
                <Button variant="secondary" onClick={() => setConfirm(true)}>
                  <UserMinus className="size-4" aria-hidden /> Unassign
                </Button>
              )}
            </div>
          </div>
        ) : canSchedule ? null : (
          <InlineNote>
            {detail.status === "SUBMITTED"
              ? "Mark the request as triaged before assigning a technician."
              : "No technician can be assigned in the request's current status."}
          </InlineNote>
        )}

        {!assignment && canSchedule && <Scheduler ctx={ctx} mode="assign" onDone={() => undefined} />}
        {assignment && canReschedule && rescheduling && <Scheduler ctx={ctx} mode="reschedule" onDone={() => setRescheduling(false)} />}
        <History ctx={ctx} />
      </section>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Unassign technician?"
        description="The request goes back to Triaged and the technician is notified."
        confirmLabel="Unassign"
        reason={{ label: "Reason (required)", minLength: 5 }}
        onConfirm={(reason) => unassign.mutateAsync({ reason })}
      />
    </Panel>
  );
}
