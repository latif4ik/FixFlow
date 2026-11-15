"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryKey, UseMutationOptions, UseQueryOptions } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import type { FieldValues, Path, UseFormReturn } from "react-hook-form";
import { api, apiFetch, isApiError, newIdempotencyKey } from "@/lib/api/client";
import type { ApiError } from "@/lib/api/client";
import type { QueryParams, RequestOptions } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";
import { toast } from "@/components/ui/toast";

/* ---------------- queries ---------------- */

export interface ApiQueryConfig<TData, TSelected = TData> extends Omit<UseQueryOptions<TData, ApiError, TSelected, QueryKey>, "queryKey" | "queryFn"> {
  /** Build the key from the org id: `(orgId) => qk.requests.detail(orgId, id)`. Must start with ['org', orgId]. */
  queryKey: (orgId: string) => QueryKey;
  /** API path under /api/v1, e.g. `/requests/${id}`. */
  path: string;
  query?: QueryParams;
}

/**
 * GET helper. Org-scoped: disabled until an org is selected, header X-Org-Id taken from the same orgId the key used,
 * so a response for org A can never be cached under org B.
 */
export function useApiQuery<TData, TSelected = TData>({ queryKey, path, query, enabled = true, ...rest }: ApiQueryConfig<TData, TSelected>) {
  const { orgId, status } = useAuth();
  return useQuery<TData, ApiError, TSelected, QueryKey>({
    ...rest,
    queryKey: orgId ? queryKey(orgId) : ["org", "none"],
    queryFn: ({ signal }) => api.get<TData>(path, query, { orgId, signal }),
    enabled: enabled && Boolean(orgId) && status === "authenticated",
  });
}

/* ---------------- mutations ---------------- */

export interface ApiMutationConfig<TData, TVars> {
  /** Describe the request for the given variables. */
  request: (vars: TVars) => { method?: RequestOptions["method"]; path: string; body?: unknown; formData?: FormData; query?: QueryParams; anonymous?: boolean };
  /** Send a fresh Idempotency-Key per mutate() call (recommended for every create/transition POST). */
  idempotent?: boolean;
  /** Query keys (or prefixes) to invalidate on success. Called with orgId and the result. */
  invalidate?: (orgId: string, data: TData, vars: TVars) => QueryKey[];
  successMessage?: string | ((data: TData, vars: TVars) => string);
  /** Toast text on failure; defaults to the server's message. Set `false` to stay silent (inline error handling). */
  errorMessage?: string | false;
  /** On a 422, map `details[{field,message}]` onto this react-hook-form instance. */
  form?: UseFormReturn<any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  onSuccess?: (data: TData, vars: TVars) => void;
  onError?: (error: ApiError, vars: TVars) => void;
  options?: Omit<UseMutationOptions<TData, ApiError, TVars>, "mutationFn" | "onSuccess" | "onError">;
}

/**
 * POST/PUT/PATCH/DELETE helper. Guarantees: no duplicate submit while pending (extra mutate() calls are ignored),
 * optional Idempotency-Key, toast on success/failure, invalidation of the given keys, 422 -> form field errors.
 * Use `mutation.isPending` to disable buttons / show spinners.
 */
export function useApiMutation<TData = unknown, TVars = void>(config: ApiMutationConfig<TData, TVars>) {
  const queryClient = useQueryClient();
  const { orgId } = useAuth();
  const cfg = useRef(config);
  useEffect(() => {
    cfg.current = config;
  });
  const inflight = useRef(false);

  const mutation = useMutation<TData, ApiError, TVars>({
    ...config.options,
    mutationFn: (vars) => {
      const r = cfg.current.request(vars);
      return apiFetch<TData>(r.path, {
        method: r.method ?? "POST",
        body: r.body,
        formData: r.formData,
        query: r.query,
        anonymous: r.anonymous,
        orgId,
        idempotencyKey: cfg.current.idempotent ? newIdempotencyKey() : undefined,
      });
    },
    onSuccess: async (data, vars) => {
      const c = cfg.current;
      if (orgId && c.invalidate) {
        await Promise.all(c.invalidate(orgId, data, vars).map((queryKey) => queryClient.invalidateQueries({ queryKey })));
      }
      const msg = typeof c.successMessage === "function" ? c.successMessage(data, vars) : c.successMessage;
      if (msg) toast.success(msg);
      c.onSuccess?.(data, vars);
    },
    onError: (error, vars) => {
      const c = cfg.current;
      const mapped = c.form ? applyServerErrors(c.form, error) : false;
      // 401 shows the session-expired screen instead of a toast.
      if (c.errorMessage !== false && !(isApiError(error) && error.status === 401) && !(mapped && isApiError(error) && error.status === 422)) {
        toast.error(c.errorMessage ?? error.message);
      }
      c.onError?.(error, vars);
    },
  });

  const { mutate, mutateAsync } = mutation;
  const guardedMutate = useCallback(
    (vars: TVars, opts?: Parameters<typeof mutate>[1]) => {
      if (inflight.current) return;
      inflight.current = true;
      mutate(vars, {
        ...opts,
        onSettled: (...a) => {
          inflight.current = false;
          opts?.onSettled?.(...a);
        },
      });
    },
    [mutate],
  );
  const guardedMutateAsync = useCallback(
    async (vars: TVars) => {
      if (inflight.current) return undefined;
      inflight.current = true;
      try {
        return await mutateAsync(vars);
      } finally {
        inflight.current = false;
      }
    },
    [mutateAsync],
  );
  return { ...mutation, mutate: guardedMutate, mutateAsync: guardedMutateAsync };
}

/* ---------------- forms ---------------- */

/**
 * Maps an API 422 (`details: [{field, message}]`) onto react-hook-form fields. Unknown fields (and non-field errors)
 * go to `root.server`. Returns true when at least one error was applied.
 */
export function applyServerErrors<T extends FieldValues>(form: UseFormReturn<T>, error: unknown): boolean {
  if (!isApiError(error)) return false;
  if (error.status !== 422 && error.status !== 409) {
    form.setError("root.server", { type: "server", message: error.message });
    return true;
  }
  const fields = error.fieldErrors;
  const known = new Set(Object.keys(form.getValues()));
  let applied = false;
  for (const fe of fields) {
    // "body.title" / "title" / "lines.0.quantity" -> strip the leading location segment if it is not a field
    const name = fe.field.replace(/^(body|query)\./, "");
    const root = name.split(".")[0] ?? name;
    if (known.has(root)) {
      form.setError(name as Path<T>, { type: "server", message: fe.message });
      applied = true;
    }
  }
  if (!applied) {
    const msg = fields.length ? fields.map((f) => `${f.field}: ${f.message}`).join("; ") : error.message;
    form.setError("root.server", { type: "server", message: msg });
  }
  return true;
}
