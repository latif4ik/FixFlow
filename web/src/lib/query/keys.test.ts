import { describe, expect, it } from "vitest";
import { qk, requestChangedPrefixes } from "./keys";

const ORG = "org-123";

function collectKeys(node: unknown, out: unknown[][] = []): unknown[][] {
  if (typeof node === "function") {
    // call with (orgId, "id-1") style args; extra args are ignored by factories that do not use them
    const key = (node as (...a: unknown[]) => unknown)(ORG, "id-1", { page: 2 });
    if (Array.isArray(key)) out.push(key);
  } else if (node && typeof node === "object") {
    Object.values(node).forEach((v) => collectKeys(v, out));
  }
  return out;
}

describe("query key factory", () => {
  it("every key starts with ['org', orgId]", () => {
    const keys = collectKeys(qk);
    expect(keys.length).toBeGreaterThan(30);
    for (const k of keys) expect(k.slice(0, 2)).toEqual(["org", ORG]);
  });

  it("request detail keys live under the requests prefix so list invalidation covers them", () => {
    expect(qk.requests.detail(ORG, "r1").slice(0, 3)).toEqual(["org", ORG, "requests"]);
    expect(qk.requests.notes(ORG, "r1").slice(0, 5)).toEqual(qk.requests.detail(ORG, "r1").slice(0, 5));
  });

  it("different orgs never share a key", () => {
    expect(qk.requests.list("a", { page: 1 })).not.toEqual(qk.requests.list("b", { page: 1 }));
  });

  it("request.changed prefixes are all org-scoped and include the detail", () => {
    const keys = requestChangedPrefixes(ORG, "r9");
    for (const k of keys) expect(k.slice(0, 2)).toEqual(["org", ORG]);
    expect(keys).toContainEqual(qk.requests.detail(ORG, "r9"));
    expect(keys).toContainEqual(qk.dashboard.all(ORG));
  });
});
