import { describe, expect, it } from "vitest";
import { safeNext } from "./auth/session";
import { ROLE_HOME, isNavActive, navFor, rolesForPath } from "./nav";

describe("role navigation", () => {
  it("maps each role to its menu", () => {
    expect(navFor("REQUESTER").map((i) => i.href)).toEqual(["/requests", "/requests/new", "/notifications"]);
    expect(navFor("DISPATCHER").map((i) => i.label)).toEqual(["Dashboard", "Request queue", "Schedule board", "Properties and assets", "Estimates", "Overdue", "Notifications"]);
    expect(navFor("ADMIN").map((i) => i.href)).toContain("/admin");
    expect(navFor("DISPATCHER").map((i) => i.href)).not.toContain("/admin");
    expect(navFor("TECHNICIAN").map((i) => i.href)).toEqual(["/jobs", "/notifications"]);
    expect(navFor("DISPATCHER").find((i) => i.href === "/overdue")?.badge).toBe("overdue");
  });
  it("every nav target is reachable by its own role and role homes are allowed", () => {
    for (const role of ["REQUESTER", "DISPATCHER", "ADMIN", "TECHNICIAN"] as const) {
      for (const item of navFor(role)) expect(rolesForPath(item.href), `${role} ${item.href}`).toContain(role);
      expect(rolesForPath(ROLE_HOME[role])).toContain(role);
    }
  });
  it("gates routes by role", () => {
    expect(rolesForPath("/admin/staff")).toEqual(["ADMIN"]);
    expect(rolesForPath("/queue")).toEqual(["DISPATCHER", "ADMIN"]);
    expect(rolesForPath("/requests/abc")).toContain("TECHNICIAN");
    expect(rolesForPath("/requests")).toEqual(["REQUESTER"]);
  });
  it("marks active items by prefix but not 'My requests' on /requests/new", () => {
    const [mine, create] = navFor("REQUESTER");
    expect(isNavActive(mine!, "/requests")).toBe(true);
    expect(isNavActive(mine!, "/requests/new")).toBe(false);
    expect(isNavActive(mine!, "/requests/abc")).toBe(true);
    expect(isNavActive(create!, "/requests/new")).toBe(true);
  });
});

describe("safeNext", () => {
  it("accepts only same-origin paths", () => {
    expect(safeNext("/queue?x=1")).toBe("/queue?x=1");
    expect(safeNext("//evil.com")).toBeNull();
    expect(safeNext("https://evil.com")).toBeNull();
    expect(safeNext(null)).toBeNull();
  });
});
