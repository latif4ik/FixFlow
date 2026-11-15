import { zodResolver } from "@hookform/resolvers/zod";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { FormField, Input, Button, FormServerError } from "@/components/ui";
import { renderWithProviders, ORG_A } from "@/test/render";
import { apiUrl, errorResponse, http, HttpResponse, server } from "@/test/server";
import { applyServerErrors, useApiMutation, useApiQuery } from "./hooks";
import { qk } from "./keys";

function CreateForm({ onDone }: { onDone?: () => void }) {
  const form = useForm<{ title: string }>({ resolver: zodResolver(z.object({ title: z.string().min(1, "Required") })), defaultValues: { title: "" } });
  const create = useApiMutation<{ id: string }, { title: string }>({
    request: (v) => ({ path: "/requests", body: v }),
    idempotent: true,
    form,
    invalidate: (orgId) => [qk.requests.all(orgId)],
    onSuccess: () => onDone?.(),
  });
  return (
    <form onSubmit={form.handleSubmit((v) => create.mutate(v))}>
      <FormField label="Title" error={form.formState.errors.title?.message}>
        <Input {...form.register("title")} />
      </FormField>
      <FormServerError form={form} />
      <Button type="submit" loading={create.isPending}>
        Save
      </Button>
    </form>
  );
}

function List() {
  const q = useApiQuery<{ items: { id: string }[] }>({ queryKey: (o) => qk.requests.list(o, {}), path: "/requests" });
  return <p>{q.data ? `count:${q.data.items.length}` : "loading"}</p>;
}

describe("useApiMutation", () => {
  it("sends an Idempotency-Key, ignores double submits while pending, and invalidates the list", async () => {
    let posts = 0;
    let key: string | null = null;
    const rows = [{ id: "1" }];
    server.use(
      http.get(apiUrl("/requests"), () => HttpResponse.json({ items: rows })),
      http.post(apiUrl("/requests"), async ({ request }) => {
        posts++;
        key = request.headers.get("idempotency-key");
        await new Promise((r) => setTimeout(r, 60));
        rows.push({ id: "2" });
        return HttpResponse.json({ id: "2" });
      }),
    );
    renderWithProviders(
      <>
        <List />
        <CreateForm />
      </>,
    );
    expect(await screen.findByText("count:1")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Title"), "Leak");
    const btn = screen.getByRole("button", { name: "Save" });
    await userEvent.dblClick(btn);
    expect(await screen.findByText("count:2")).toBeInTheDocument();
    expect(posts).toBe(1);
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("maps 422 details onto form fields and keeps the form usable", async () => {
    server.use(http.post(apiUrl("/requests"), () => errorResponse(422, "validation_error", "Request validation failed.", [{ field: "title", message: "Title already exists" }])));
    renderWithProviders(<CreateForm />);
    await userEvent.type(screen.getByLabelText("Title"), "Dup");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Title already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());
  });
});

describe("useApiQuery", () => {
  it("is keyed by org and sends the org header it was keyed with", async () => {
    let org: string | null = null;
    server.use(
      http.get(apiUrl("/requests"), ({ request }) => {
        org = request.headers.get("x-org-id");
        return HttpResponse.json({ items: [] });
      }),
    );
    const { queryClient } = renderWithProviders(<List />);
    await screen.findByText("count:0");
    expect(org).toBe(ORG_A.id);
    expect(queryClient.getQueryCache().getAll().every((q) => q.queryKey[0] === "org" && q.queryKey[1] === ORG_A.id)).toBe(true);
  });
});

describe("applyServerErrors", () => {
  it("returns false for non-API errors", () => {
    expect(applyServerErrors({} as never, new Error("x"))).toBe(false);
  });
});
