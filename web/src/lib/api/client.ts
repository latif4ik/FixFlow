import { apiAuth } from "./session-store";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const API_PREFIX = "/api/v1";

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(init: { status: number; code: string; message: string; details?: unknown; requestId?: string | null }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? null;
    this.requestId = init.requestId ?? null;
  }

  /** 422 details as [{field, message}]; empty for other errors. */
  get fieldErrors(): FieldError[] {
    if (!Array.isArray(this.details)) return [];
    return this.details.filter(
      (d): d is FieldError =>
        typeof d === "object" && d !== null && typeof (d as FieldError).field === "string" && typeof (d as FieldError).message === "string",
    );
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

export type QueryParams = Record<string, string | number | boolean | null | undefined | readonly (string | number)[]>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: QueryParams;
  /** JSON body. */
  body?: unknown;
  /** Multipart body (do not set content-type; the browser adds the boundary). */
  formData?: FormData;
  /** Send an Idempotency-Key header. Use `newIdempotencyKey()`. */
  idempotencyKey?: string;
  /** Override the X-Org-Id header (hooks pass the orgId their query key was built from). */
  orgId?: string | null;
  /** Skip Authorization/X-Org-Id (login). */
  anonymous?: boolean;
  signal?: AbortSignal;
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function buildUrl(path: string, query?: QueryParams): string {
  const url = `${API_URL}${API_PREFIX}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.append(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `${url}?${qs}` : url;
}

function headersFor(opts: RequestOptions, json: boolean): Headers {
  const h = new Headers({ Accept: "application/json" });
  if (json) h.set("Content-Type", "application/json");
  if (!opts.anonymous) {
    const { token, orgId } = apiAuth.get();
    if (token) h.set("Authorization", `Bearer ${token}`);
    const org = opts.orgId ?? orgId;
    if (org) h.set("X-Org-Id", org);
  }
  if (opts.idempotencyKey) h.set("Idempotency-Key", opts.idempotencyKey);
  return h;
}

async function toApiError(res: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    /* non-JSON body */
  }
  const env = (payload as { error?: { code?: string; message?: string; details?: unknown; request_id?: string } } | null)?.error;
  return new ApiError({
    status: res.status,
    code: env?.code ?? `http_${res.status}`,
    message: env?.message ?? res.statusText ?? "Request failed",
    details: env?.details,
    requestId: env?.request_id ?? res.headers.get("x-request-id"),
  });
}

async function doFetch(path: string, opts: RequestOptions): Promise<Response> {
  const hasJson = opts.body !== undefined && !opts.formData;
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      headers: headersFor(opts, hasJson),
      body: opts.formData ?? (hasJson ? JSON.stringify(opts.body) : undefined),
      signal: opts.signal,
      cache: "no-store",
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError({ status: 0, code: "network_error", message: "Cannot reach the server. Check your connection and try again." });
  }
  if (!res.ok) {
    const err = await toApiError(res);
    if (res.status === 401 && !opts.anonymous) apiAuth.notifyUnauthorized();
    throw err;
  }
  return res;
}

/** JSON request. Returns undefined for 204. Throws ApiError. */
export async function apiFetch<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await doFetch(path, opts);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Authenticated binary download (e.g. /files/{id}). */
export async function apiBlob(path: string, opts: RequestOptions = {}): Promise<Blob> {
  const res = await doFetch(path, opts);
  return res.blob();
}

type Opts = Omit<RequestOptions, "method" | "body">;
export const api = {
  get: <T>(path: string, query?: QueryParams, opts: Opts = {}) => apiFetch<T>(path, { ...opts, query }),
  post: <T>(path: string, body?: unknown, opts: Opts = {}) => apiFetch<T>(path, { ...opts, method: "POST", body: body ?? {} }),
  put: <T>(path: string, body?: unknown, opts: Opts = {}) => apiFetch<T>(path, { ...opts, method: "PUT", body: body ?? {} }),
  patch: <T>(path: string, body?: unknown, opts: Opts = {}) => apiFetch<T>(path, { ...opts, method: "PATCH", body: body ?? {} }),
  delete: <T>(path: string, opts: Opts = {}) => apiFetch<T>(path, { ...opts, method: "DELETE" }),
  upload: <T>(path: string, formData: FormData, opts: Opts = {}) => apiFetch<T>(path, { ...opts, method: "POST", formData }),
};
