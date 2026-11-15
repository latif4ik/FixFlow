"use client";

import {
  AlertTriangle,
  Ban,
  CalendarCheck,
  CheckCircle2,
  CircleDashed,
  CircleDot,
  ClipboardCheck,
  Clock,
  Flag,
  Loader2,
  PauseCircle,
  PlayCircle,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/cn";
import { useNow } from "@/lib/use-now";
import { formatDateTime, formatDuration, formatMoney, formatRelative, initials } from "@/lib/format";
import type { DateStyle } from "@/lib/format";
import type { Priority, RequestStatus } from "@/lib/api/types";

/* ---------- Card / Panel (design panel style) ---------- */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-border bg-surface shadow-panel", className)} {...props} />;
}

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
  as: Tag = "section",
  id,
}: {
  id?: string;
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  as?: "section" | "div" | "aside";
}) {
  return (
    <Tag id={id} tabIndex={id ? -1 : undefined} className={cn("rounded-xl border border-border bg-surface shadow-panel outline-none", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3.5">
          {title && <h2 className="font-heading text-base font-bold text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </Tag>
  );
}

/* ---------- Badge ---------- */
export type Tone = "neutral" | "primary" | "danger" | "warning" | "info" | "success";
const TONES: Record<Tone, string> = {
  neutral: "bg-canvas-2 text-text",
  primary: "bg-primary-tint text-primary-dark",
  success: "bg-primary-tint text-primary-dark",
  danger: "bg-danger-tint text-danger-dark",
  warning: "bg-warning-tint text-warning-dark",
  info: "bg-info-tint text-info",
};

export function Badge({ tone = "neutral", icon: Icon, children, className }: { tone?: Tone; icon?: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill px-2.5 py-1 text-[13px] font-semibold", TONES[tone], className)}>
      {Icon && <Icon className="size-3.5 shrink-0" aria-hidden />}
      {children}
    </span>
  );
}

/* ---------- Status / Priority / SLA (never color-only: icon + text) ---------- */
export const STATUS_META: Record<RequestStatus, { label: string; tone: Tone; icon: LucideIcon }> = {
  SUBMITTED: { label: "Submitted", tone: "neutral", icon: CircleDashed },
  TRIAGED: { label: "Triaged", tone: "info", icon: ClipboardCheck },
  SCHEDULED: { label: "Scheduled", tone: "info", icon: CalendarCheck },
  ACCEPTED: { label: "Accepted", tone: "primary", icon: ShieldCheck },
  IN_PROGRESS: { label: "In progress", tone: "primary", icon: PlayCircle },
  BLOCKED: { label: "Blocked", tone: "warning", icon: PauseCircle },
  COMPLETED: { label: "Completed", tone: "success", icon: CheckCircle2 },
  CLOSED: { label: "Closed", tone: "neutral", icon: CheckCircle2 },
  REOPENED: { label: "Reopened", tone: "warning", icon: RotateCcw },
  CANCELED: { label: "Canceled", tone: "neutral", icon: Ban },
};

export function StatusBadge({ status, className }: { status: RequestStatus; className?: string }) {
  const m = STATUS_META[status];
  return (
    <Badge tone={m.tone} icon={m.icon} className={className}>
      {m.label}
    </Badge>
  );
}

const PRIORITY_META: Record<Priority, { label: string; tone: Tone; icon: LucideIcon }> = {
  HIGH: { label: "High priority", tone: "danger", icon: Flag },
  NORMAL: { label: "Normal priority", tone: "neutral", icon: Flag },
  LOW: { label: "Low priority", tone: "neutral", icon: Flag },
};

export function PriorityBadge({ priority, className }: { priority: Priority; className?: string }) {
  const m = PRIORITY_META[priority];
  return (
    <Badge tone={m.tone} icon={m.icon} className={className}>
      {m.label}
    </Badge>
  );
}

export type SlaStateValue = "ON_TRACK" | "AT_RISK" | "OVERDUE" | "PAUSED";

/**
 * SLA chip, e.g. "SLA at risk · due 11:32 · 50 min left". Pass `remainingMinutes` / `overdueByMinutes` from the
 * API `sla` object when available; otherwise they are derived from `dueAt` and the current time.
 */
export function SlaBadge({
  state,
  dueAt,
  remainingMinutes,
  overdueByMinutes,
  className,
  tz,
}: {
  state: string | null | undefined;
  dueAt?: string | null;
  remainingMinutes?: number | null;
  overdueByMinutes?: number | null;
  className?: string;
  tz?: string;
}) {
  const auth = useAuth();
  const zone = tz ?? auth.timezone;
  const now = useNow();
  const due = dueAt ? formatDateTime(dueAt, zone, now > 0 && sameDay(dueAt, zone, now) ? "time" : "short") : null;
  const derived = dueAt && now > 0 ? Math.round((new Date(dueAt).getTime() - now) / 60000) : null;
  const s = (state ?? "ON_TRACK") as SlaStateValue;
  const parts: string[] = [];
  let tone: Tone = "success";
  let icon: LucideIcon = ShieldCheck;
  switch (s) {
    case "AT_RISK": {
      tone = "warning";
      icon = AlertTriangle;
      parts.push("SLA at risk");
      if (due) parts.push(`due ${due}`);
      const left = remainingMinutes ?? derived;
      if (left !== null && left !== undefined && left >= 0) parts.push(`${formatDuration(left)} left`);
      break;
    }
    case "OVERDUE": {
      tone = "danger";
      icon = AlertTriangle;
      parts.push("Overdue");
      if (due) parts.push(`due ${due}`);
      const late = overdueByMinutes ?? (derived !== null ? -derived : null);
      if (late !== null && late !== undefined && late > 0) parts.push(`${formatDuration(late)} late`);
      break;
    }
    case "PAUSED":
      tone = "neutral";
      icon = PauseCircle;
      parts.push("SLA paused");
      break;
    default:
      parts.push("SLA on track");
      if (due) parts.push(`due ${due}`);
  }
  return (
    <Badge tone={tone} icon={icon} className={className}>
      {parts.join(" · ")}
    </Badge>
  );
}

function sameDay(iso: string, tz: string, now: number): boolean {
  return formatDateTime(iso, tz, "date") === formatDateTime(new Date(now), tz, "date");
}

/* ---------- Money / DateTime ---------- */
export function Money({ minor, currency = "KGS", className }: { minor: number; currency?: string; className?: string }) {
  return <span className={cn("whitespace-nowrap tabular-nums", className)}>{formatMoney(minor, currency)}</span>;
}

/** Renders an instant in the ORG timezone (override with `tz`). `relative` shows "in 50 min" / "12 min ago". */
export function DateTime({ value, style = "datetime", relative, tz, className }: { value: string | Date | null | undefined; style?: DateStyle; relative?: boolean; tz?: string; className?: string }) {
  const auth = useAuth();
  if (!value) return <span className={className}>-</span>;
  const iso = value instanceof Date ? value.toISOString() : value;
  return (
    <time dateTime={iso} title={formatDateTime(value, tz ?? auth.timezone, "datetime")} className={cn("whitespace-nowrap", className)}>
      {relative ? formatRelative(value) : formatDateTime(value, tz ?? auth.timezone, style)}
    </time>
  );
}

/* ---------- Avatar ---------- */
export function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-flex size-8 shrink-0 items-center justify-center rounded-pill bg-primary-tint-2 text-xs font-bold text-deep", className)}
    >
      {initials(name)}
    </span>
  );
}

/* ---------- Loading / Empty / Error ---------- */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-canvas-2", className)} />;
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-2 p-10 text-sm text-muted">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function EmptyState({ title, description, action, icon: Icon = CircleDot }: { title: ReactNode; description?: ReactNode; action?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <Icon className="size-8 text-subtle" aria-hidden />
      <p className="font-heading text-base font-bold text-ink">{title}</p>
      {description && <p className="max-w-md text-sm text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export interface ErrorLike {
  message: string;
  requestId?: string | null;
  status?: number;
}

export function ErrorState({ error, title = "Something went wrong", onRetry, className }: { error?: ErrorLike | null; title?: string; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" className={cn("flex flex-col items-start gap-2 rounded-xl border border-danger/30 bg-danger-tint p-5", className)}>
      <p className="flex items-center gap-2 font-heading text-base font-bold text-danger-dark">
        <XCircle className="size-5" aria-hidden />
        {title}
      </p>
      {error && <p className="text-sm text-danger-dark">{error.message}</p>}
      {error?.requestId && <p className="text-xs text-danger-dark/80">Request ID: {error.requestId}</p>}
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-1 inline-flex h-9 items-center rounded-md border border-danger-dark/40 bg-surface px-3 text-sm font-semibold text-danger-dark hover:bg-canvas">
          Try again
        </button>
      )}
    </div>
  );
}

export function InlineNote({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <p className={cn("flex items-start gap-2 rounded-md px-3 py-2 text-[13px]", TONES[tone])}>
      <Clock className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}
