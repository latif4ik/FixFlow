"use client";

import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import type { Role } from "@/lib/api/types";
import { requesterActions } from "./requester";
import { staffActions } from "./staff";
import type { ActionPlacement, RequestActionContext, RequestActionDefinition } from "./types";

export type { ActionPlacement, RequestActionContext, RequestActionDefinition, RequestActionProps } from "./types";

/** Roles served by each registration map (a definition may narrow further with `roles`). */
const REQUESTER_ROLES: readonly Role[] = ["REQUESTER"];
const STAFF_ROLES: readonly Role[] = ["DISPATCHER", "ADMIN", "TECHNICIAN"];

function applicable(def: RequestActionDefinition, mapRoles: readonly Role[], ctx: RequestActionContext): boolean {
  if (!mapRoles.includes(ctx.role)) return false;
  if (def.roles && !def.roles.includes(ctx.role)) return false;
  if (def.show) return def.show(ctx);
  return (def.when ?? "allowed") === "always" || ctx.allowed.has(def.name);
}

/** Pure selector (unit-tested): definitions to render for a placement, ordered. */
export function selectActions(ctx: RequestActionContext, placement: ActionPlacement, maps?: { requester: RequestActionDefinition[]; staff: RequestActionDefinition[] }): RequestActionDefinition[] {
  const req = maps?.requester ?? requesterActions;
  const staff = maps?.staff ?? staffActions;
  return [
    ...req.filter((d) => applicable(d, REQUESTER_ROLES, ctx)),
    ...staff.filter((d) => applicable(d, STAFF_ROLES, ctx)),
  ]
    .filter((d) => d.placement === placement)
    .sort((a, b) => (a.order ?? 100) - (b.order ?? 100));
}

class ActionBoundary extends Component<{ label: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Request action "${this.props.label}" crashed`, error.message, info.componentStack);
  }
  render() {
    if (this.state.failed) {
      return (
        <p role="alert" className="rounded-md bg-danger-tint px-3 py-2 text-sm text-danger-dark">
          The &ldquo;{this.props.label}&rdquo; panel failed to load. Reload the page to try again.
        </p>
      );
    }
    return this.props.children;
  }
}

/** Renders every registered action/panel for a placement. Each is isolated by an error boundary. */
export function RequestActionSlot({ placement, ctx, className }: { placement: ActionPlacement; ctx: RequestActionContext; className?: string }) {
  const defs = selectActions(ctx, placement);
  if (defs.length === 0) return null;
  return (
    <div className={className}>
      {defs.map((d) => {
        const C = d.component;
        return (
          <ActionBoundary key={d.name} label={d.label}>
            <C ctx={ctx} />
          </ActionBoundary>
        );
      })}
    </div>
  );
}
