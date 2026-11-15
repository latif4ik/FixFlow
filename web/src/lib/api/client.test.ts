import { describe, expect, it, vi } from "vitest";
import { server, http, HttpResponse, apiUrl, errorResponse } from "@/test/server";
import { api, ApiError, apiFetch, newIdempotencyKey } from "./client";
import { apiAuth } from "./session-store";

describe("api client", () => {
  it("parses the error envelope into ApiError", async () => {
    server.use(http.get(apiUrl("/requests/x"), () => errorResponse(404, "not_found", "Request not found.", null, "rid-42")));
    const err = await api.get("/requests/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect(e).toMatchObject({ status: 404, code: "not_found", message: "Request not found.", requestId: "rid-42" });
  });

  it("exposes 422 details as fieldErrors", async () => {
    server.use(http.post(apiUrl("/requests"), () => errorResponse(422, "validation_error", "Request validation failed.", [{ field: "title", message: "Too short" }])));
    const e = (await api.post("/requests", {}).catch((x: unknown) => x)) as ApiError;
    expect(e.fieldErrors).toEqual([{ field: "title", message: "Too short" }]);
  });

  it("401 on an authenticated call triggers session expiry; login 401 does not", async () => {
    const onExpired = vi.fn();
    apiAuth.setUnauthorizedHandler(onExpired);
    server.use(
      http.get(apiUrl("/me"), () => errorResponse(401, "unauthorized", "Session expired")),
      http.post(apiUrl("/auth/login"), () => errorResponse(401, "invalid_credentials", "Wrong email or password")),
    );
    await expect(api.get("/me")).rejects.toMatchObject({ status: 401 });
    expect(onExpired).toHaveBeenCalledTimes(1);
    await expect(apiFetch("/auth/login", { method: "POST", body: {}, anonymous: true })).rejects.toMatchObject({ code: "invalid_credentials" });
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  it("maps connection failures to network_error", async () => {
    server.use(http.get(apiUrl("/me"), () => HttpResponse.error()));
    await expect(api.get("/me")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });

  it("sends Authorization, X-Org-Id and Idempotency-Key headers", async () => {
    apiAuth.set({ token: "tok", orgId: "org-1" });
    let seen: Headers | null = null;
    server.use(
      http.post(apiUrl("/requests"), ({ request }) => {
        seen = request.headers;
        return HttpResponse.json({ ok: true });
      }),
    );
    const key = newIdempotencyKey();
    await api.post("/requests", { a: 1 }, { idempotencyKey: key });
    const h = seen as unknown as Headers;
    expect(h.get("authorization")).toBe("Bearer tok");
    expect(h.get("x-org-id")).toBe("org-1");
    expect(h.get("idempotency-key")).toBe(key);
    expect(h.get("content-type")).toBe("application/json");
  });

  it("uploads multipart without a JSON content-type", async () => {
    let ct: string | null = null;
    server.use(
      http.post(apiUrl("/requests/1/files"), ({ request }) => {
        ct = request.headers.get("content-type");
        return HttpResponse.json({ id: "f1" });
      }),
    );
    const fd = new FormData();
    fd.append("file", new Blob(["x"], { type: "image/png" }), "a.png");
    await api.upload("/requests/1/files", fd);
    expect(ct).toMatch(/^multipart\/form-data; boundary=/);
  });
});
