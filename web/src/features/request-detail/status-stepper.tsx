import { Check } from "lucide-react";
import { STATUS_META } from "@/components/ui";
import type { RequestStatus } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const FLOW: RequestStatus[] = ["SUBMITTED", "TRIAGED", "SCHEDULED", "ACCEPTED", "IN_PROGRESS", "COMPLETED", "CLOSED"];

/** Progress through the happy path. BLOCKED/REOPENED map to their nearest stage; CANCELED shows a single note. */
export function StatusStepper({ status }: { status: RequestStatus }) {
  if (status === "CANCELED") {
    return <p className="text-sm text-muted">This request was canceled.</p>;
  }
  const mapped: RequestStatus = status === "BLOCKED" ? "IN_PROGRESS" : status === "REOPENED" ? "TRIAGED" : status;
  const current = FLOW.indexOf(mapped);
  return (
    <ol aria-label="Request progress" className="flex gap-1 overflow-x-auto pb-1">
      {FLOW.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li
            key={s}
            aria-current={active ? "step" : undefined}
            className={cn(
              "flex min-w-fit flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-semibold",
              done ? "bg-primary-tint text-primary-dark" : active ? "bg-primary text-white" : "bg-canvas-2 text-muted",
            )}
          >
            {done && <Check className="size-3.5" aria-hidden />}
            {STATUS_META[s].label}
            {done && <span className="sr-only"> (done)</span>}
            {active && <span className="sr-only"> (current{status !== mapped ? `: ${STATUS_META[status].label}` : ""})</span>}
          </li>
        );
      })}
    </ol>
  );
}
