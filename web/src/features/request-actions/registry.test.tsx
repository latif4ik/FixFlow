import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RequestDetail } from "@/lib/api/types";
import { RequestActionSlot, selectActions } from "./registry";
import type { RequestActionContext, RequestActionDefinition } from "./registry";

const detail = { id: "r1", display_id: "REQ-1", allowed_actions: ["cancel", "assign"] } as unknown as RequestDetail;
const ctx = (role: RequestActionContext["role"], allowed: string[] = ["cancel", "assign"]): RequestActionContext => ({
  requestId: "r1",
  detail,
  orgId: "o1",
  role,
  timezone: "UTC",
  allowed: new Set(allowed),
});
const C = ({ ctx }: { ctx: RequestActionContext }) => <p>{`panel for ${ctx.role}`}</p>;
const def = (name: string, p: Partial<RequestActionDefinition> = {}): RequestActionDefinition => ({ name, label: name, component: C, placement: "sidebar", ...p });

describe("action registry", () => {
  const maps = {
    requester: [def("cancel", { order: 5 }), def("feedback", { when: "always" })],
    staff: [def("assign", { order: 1 }), def("triage"), def("hdr", { placement: "header", when: "always" })],
  };

  it("shows only allowed actions, filtered by map role, ordered", () => {
    expect(selectActions(ctx("DISPATCHER"), "sidebar", maps).map((d) => d.name)).toEqual(["assign"]);
    expect(selectActions(ctx("REQUESTER"), "sidebar", maps).map((d) => d.name)).toEqual(["cancel", "feedback"]);
    expect(selectActions(ctx("REQUESTER", []), "sidebar", maps).map((d) => d.name)).toEqual(["feedback"]);
  });

  it("filters by placement and honours show()", () => {
    expect(selectActions(ctx("ADMIN"), "header", maps).map((d) => d.name)).toEqual(["hdr"]);
    const custom = { requester: [], staff: [def("x", { show: () => false }), def("y", { show: () => true })] };
    expect(selectActions(ctx("ADMIN"), "sidebar", custom).map((d) => d.name)).toEqual(["y"]);
  });

  it("renders nothing for a partial context (no registered actions match)", () => {
    const { container } = render(<RequestActionSlot placement="sidebar" ctx={ctx("DISPATCHER")} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/panel for/)).not.toBeInTheDocument();
  });
});

