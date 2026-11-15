import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { apiAuth } from "@/lib/api/session-store";
import { mockRouter } from "@/test/navigation-mock";
import { membership, ORG_A, ORG_B, renderWithProviders } from "@/test/render";
import { errorResponse, http, HttpResponse, server, apiUrl } from "@/test/server";
import { LoginForm } from "./login-form";

const user = { id: "u1", email: "d@x.demo", full_name: "Dee" };

describe("LoginForm", () => {
  it("validates required fields inline and does not call the API", async () => {
    let called = false;
    server.use(http.post(apiUrl("/auth/login"), () => ((called = true), HttpResponse.json({}))));
    renderWithProviders(<LoginForm />, { session: null });
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    expect(screen.getByLabelText(/Email/)).toHaveAttribute("aria-invalid", "true");
    expect(called).toBe(false);
  });

  it("logs in with one membership and routes to that role's home", async () => {
    server.use(
      http.post(apiUrl("/auth/login"), async ({ request }) => {
        const body = (await request.json()) as { email: string };
        expect(body.email).toBe("d@x.demo");
        expect(request.headers.get("authorization")).toBeNull();
        return HttpResponse.json({ token: "tok-1", expires_at: new Date(Date.now() + 3600_000).toISOString(), user, memberships: [membership("DISPATCHER", ORG_A)] });
      }),
    );
    renderWithProviders(<LoginForm />, { session: null });
    await userEvent.type(screen.getByLabelText(/Email/), "d@x.demo");
    await userEvent.type(screen.getByLabelText(/Password/), "demo1234");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith("/dashboard"));
    expect(apiAuth.get()).toEqual({ token: "tok-1", orgId: ORG_A.id });
    expect(JSON.parse(window.sessionStorage.getItem("fixflow.session")!).token).toBe("tok-1");
  });

  it("routes requesters to /requests and multi-org users to /select-org", async () => {
    server.use(
      http.post(apiUrl("/auth/login"), () =>
        HttpResponse.json({ token: "t", expires_at: new Date(Date.now() + 3600_000).toISOString(), user, memberships: [membership("REQUESTER", ORG_A), membership("DISPATCHER", ORG_B)] }),
      ),
    );
    renderWithProviders(<LoginForm />, { session: null });
    await userEvent.type(screen.getByLabelText(/Email/), "d@x.demo");
    await userEvent.type(screen.getByLabelText(/Password/), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith("/select-org"));
    expect(apiAuth.get().orgId).toBeNull();
  });

  it("shows the server error when credentials are wrong and stays on the form", async () => {
    server.use(http.post(apiUrl("/auth/login"), () => errorResponse(401, "invalid_credentials", "Invalid email or password.")));
    renderWithProviders(<LoginForm />, { session: null });
    await userEvent.type(screen.getByLabelText(/Email/), "d@x.demo");
    await userEvent.type(screen.getByLabelText(/Password/), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(mockRouter.replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  async function loginAs(role: "REQUESTER" | "DISPATCHER", search: Record<string, string>) {
    server.use(
      http.post(apiUrl("/auth/login"), () => HttpResponse.json({ token: "t", expires_at: new Date(Date.now() + 3600_000).toISOString(), user, memberships: [membership(role, ORG_A)] })),
    );
    renderWithProviders(<LoginForm />, { session: null, route: "/login", search });
    await userEvent.type(screen.getByLabelText(/Email/), "d@x.demo");
    await userEvent.type(screen.getByLabelText(/Password/), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  }

  it("honors ?next only when the role may view that path", async () => {
    await loginAs("DISPATCHER", { next: "/schedule" });
    await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith("/schedule"));
  });

  it("ignores ?next the role cannot access and goes to the role home (requester after a dispatcher signed out)", async () => {
    await loginAs("REQUESTER", { next: "/schedule" });
    await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith("/requests"));
    expect(mockRouter.replace).not.toHaveBeenCalledWith("/schedule");
  });
});
