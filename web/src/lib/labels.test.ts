import { describe, expect, it } from "vitest";
import { estimateStatusLabel, humanize, requestStatusText, rowActionFor, rowActionHref } from "./labels";

describe("labels", () => {
  it("humanizes enums", () => {
    expect(humanize("AWAITING_APPROVAL")).toBe("Awaiting approval");
    expect(["DRAFT", "AWAITING_APPROVAL", "APPROVED", "REJECTED", "SUPERSEDED"].map(estimateStatusLabel)).toEqual(["Draft", "Awaiting approval", "Approved", "Rejected", "Superseded"]);
    expect(requestStatusText("IN_PROGRESS")).toBe("in progress");
  });
  it("only TRIAGED requests get Smart assign; SUBMITTED/REOPENED get Triage", () => {
    expect(rowActionFor("TRIAGED")).toBe("assign");
    expect(rowActionFor("SUBMITTED")).toBe("triage");
    expect(rowActionFor("REOPENED")).toBe("triage");
    expect(rowActionFor("IN_PROGRESS")).toBe("open");
    expect(rowActionHref("x", "SUBMITTED")).toBe("/requests/x#triage");
    expect(rowActionHref("x", "TRIAGED")).toBe("/requests/x#assign");
  });
});
