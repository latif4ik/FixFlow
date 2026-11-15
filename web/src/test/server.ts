import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { API_PREFIX, API_URL } from "@/lib/api/client";

/** MSW server shared by all tests. Add per-test handlers with `server.use(...)`. */
export const server = setupServer();

/** Absolute URL of an API path, e.g. apiUrl("/requests/1") (MSW matches query-less). */
export const apiUrl = (path: string) => `${API_URL}${API_PREFIX}${path}`;

export { http, HttpResponse };

/** Standard error envelope as the backend returns it. */
export function errorResponse(status: number, code: string, message: string, details: unknown = null, requestId = "req-test-1") {
  return HttpResponse.json({ error: { code, message, details, request_id: requestId } }, { status });
}

/** Handler helpers: `server.use(...jsonHandlers({ "GET /notifications/unread-count": { unread: 2 } }))`. */
export function jsonHandlers(map: Record<string, unknown>) {
  return Object.entries(map).map(([key, body]) => {
    const [method, path] = key.split(" ") as [string, string];
    const fn = http[method.toLowerCase() as "get" | "post" | "put" | "patch" | "delete"];
    return fn(apiUrl(path!), () => HttpResponse.json(body as Record<string, unknown>));
  });
}
