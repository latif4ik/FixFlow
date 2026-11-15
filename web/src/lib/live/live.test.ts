import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { qk } from "@/lib/query/keys";
import { backoffDelay, handleLiveEvent } from "./live";

function setup() {
  const qc = new QueryClient();
  const keys = {
    list: qk.requests.list("o1", { page: 1 }),
    detail: qk.requests.detail("o1", "r1"),
    otherDetail: qk.requests.detail("o1", "r2"),
    dash: qk.dashboard.overdueCount("o1"),
    notif: qk.notifications.unreadCount("o1"),
    otherOrg: qk.requests.list("o2", { page: 1 }),
  };
  for (const k of Object.values(keys)) qc.setQueryData(k, 1);
  const stale = (k: readonly unknown[]) => qc.getQueryState(k)?.isInvalidated === true;
  return { qc, keys, stale };
}

describe("live events", () => {
  it("request.changed invalidates requests, that detail and dashboards of the org only", () => {
    const { qc, keys, stale } = setup();
    handleLiveEvent(qc, "o1", "request.changed", JSON.stringify({ request_id: "r1" }));
    expect(stale(keys.list)).toBe(true);
    expect(stale(keys.detail)).toBe(true);
    expect(stale(keys.dash)).toBe(true);
    expect(stale(keys.notif)).toBe(false);
    expect(stale(keys.otherOrg)).toBe(false);
  });

  it("notification.created invalidates notifications only", () => {
    const { qc, keys, stale } = setup();
    handleLiveEvent(qc, "o1", "notification.created", JSON.stringify({ notification_id: "n" }));
    expect(stale(keys.notif)).toBe(true);
    expect(stale(keys.list)).toBe(false);
  });

  it("resync invalidates everything for the org", () => {
    const { qc, keys, stale } = setup();
    handleLiveEvent(qc, "o1", "resync", null);
    for (const [name, k] of Object.entries(keys)) expect(stale(k), name).toBe(name !== "otherOrg");
  });

  it("backs off 1s -> 30s", () => {
    expect([0, 1, 2, 3, 4, 5, 6, 10].map(backoffDelay)).toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000]);
  });
});
