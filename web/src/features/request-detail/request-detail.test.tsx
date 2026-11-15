import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fakeSession, renderWithProviders } from "@/test/render";
import { apiUrl, errorResponse, http, HttpResponse, server } from "@/test/server";
import { RequestDetailPage } from "./request-detail-page";

const base = {
  id: "r1",
  number: 1,
  display_id: "REQ-1",
  title: "AC leaking onto server rack",
  status: "SCHEDULED",
  priority: "HIGH",
  category: { id: "c", name: "HVAC" },
  property: { id: "p", name: "Ala-Too Business Center", address: "1 Main" },
  asset: { id: "a", code: "AC-204", name: "Split AC unit" },
  requester: { membership_id: "m", name: "Marat A." },
  created_at: "2026-11-15T03:02:00Z",
  updated_at: "2026-11-15T03:02:00Z",
  sla_state: "AT_RISK",
  sla_due_at: new Date(Date.now() + 50 * 60_000).toISOString(),
  description: "Dripping onto the rack.",
  notes: [
    { id: "n1", request_id: "r1", author: { membership_id: "m", name: "Marat A." }, visibility: "PUBLIC", kind: "GENERAL", body: "Please hurry", created_at: "2026-11-15T03:03:00Z", attachments: [] },
    { id: "n2", request_id: "r1", author: { membership_id: "d", name: "Aibek D." }, visibility: "INTERNAL", kind: "TRIAGE", body: "Switch AC off first", created_at: "2026-11-15T03:10:00Z", attachments: [] },
  ],
  files: [],
  timeline: [
    { id: "t1", type: "REQUEST_CREATED", label: "Request created", actor: { membership_id: "m", name: "Marat A." }, from_status: null, to_status: "SUBMITTED", data: null, created_at: "2026-11-15T03:02:00Z" },
    { id: "t2", type: "STATUS_CHANGED", label: "Status changed", actor: { membership_id: "d", name: "Aibek D." }, from_status: "SUBMITTED", to_status: "TRIAGED", data: null, created_at: "2026-11-15T03:20:00Z" },
  ],
  allowed_actions: [],
  assignment: null,
  estimate: { id: "e", version: 1, status: "DRAFT", total_minor: 494000, currency: "KGS", labor_minutes: 60, labor_cost_minor: 120000, materials_total_minor: 374000, lines: [] },
  materials: [],
  feedback: null,
};

describe("request detail shell", () => {
  it("renders header chips, facts, activity labels and the estimate in org-local time and money format", async () => {
    server.use(http.get(apiUrl("/requests/r1"), () => HttpResponse.json(base)));
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: fakeSession({ role: "DISPATCHER" }) });
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("AC leaking onto server rack");
    expect(screen.getAllByText("Scheduled").length).toBeGreaterThan(0);
    expect(screen.getByText("High priority")).toBeInTheDocument();
    expect(screen.getByText(/SLA at risk · due/)).toBeInTheDocument();
    expect(screen.getByText("AC-204 · Split AC unit")).toBeInTheDocument();
    expect(screen.getAllByText("15 Nov 2026, 09:02").length).toBeGreaterThan(0); // 03:02Z in Asia/Bishkek
    expect(screen.getByText("Status changed from Submitted to Triaged")).toBeInTheDocument();
    expect(screen.getByText("4 940.00 KGS")).toBeInTheDocument();
    expect(screen.getByText(/Internal note · hidden from requester/)).toBeInTheDocument();
  });

  it("offers staff a visibility choice but requesters only public notes", async () => {
    server.use(http.get(apiUrl("/requests/r1"), () => HttpResponse.json(base)));
    const staff = renderWithProviders(<RequestDetailPage requestId="r1" />, { session: fakeSession({ role: "DISPATCHER" }) });
    const form = await screen.findByRole("form", { name: "Add a note" });
    expect(within(form).getByRole("radio", { name: /Internal/ })).toBeInTheDocument();
    staff.unmount();
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: fakeSession({ role: "REQUESTER" }) });
    const form2 = await screen.findByRole("form", { name: "Add a note" });
    expect(within(form2).queryByRole("radio")).not.toBeInTheDocument();
  });

  it("shows a clear not-found state with the request id", async () => {
    server.use(http.get(apiUrl("/requests/r1"), () => errorResponse(404, "not_found", "No such request", null, "rid-9")));
    renderWithProviders(<RequestDetailPage requestId="r1" />);
    expect(await screen.findByText("Request not found")).toBeInTheDocument();
    expect(screen.getByText(/Request ID: rid-9/)).toBeInTheDocument();
  });

  it("shows human-readable estimate status, never the raw enum", async () => {
    server.use(http.get(apiUrl("/requests/r1"), () => HttpResponse.json({ ...base, estimate: { ...base.estimate, status: "AWAITING_APPROVAL" } })));
    renderWithProviders(<RequestDetailPage requestId="r1" />, { session: fakeSession({ role: "DISPATCHER" }) });
    expect(await screen.findByText("Version 1 · Awaiting approval")).toBeInTheDocument();
    expect(screen.queryByText(/Awaiting_approval/i)).not.toBeInTheDocument();
  });
});
