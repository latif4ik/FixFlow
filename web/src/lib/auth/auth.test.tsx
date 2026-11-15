import { act, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiAuth } from "@/lib/api/session-store";
import { fakeSession, membership, ORG_A, ORG_B, renderWithProviders } from "@/test/render";
import { mockRouter } from "@/test/navigation-mock";
import { useAuth } from "./auth-context";
import { RouteGuard } from "./route-guard";

function Probe() {
  const a = useAuth();
  return (
    <div>
      <p data-testid="org">{a.orgName}</p>
      <button onClick={() => a.switchOrg(ORG_B.id)}>switch</button>
    </div>
  );
}

describe("org switching", () => {
  it("clears the query cache, updates the API org header and routes to the new role home", () => {
    const session = fakeSession({ memberships: [membership("REQUESTER", ORG_A), membership("DISPATCHER", ORG_B)], orgId: ORG_A.id });
    const { queryClient } = renderWithProviders(<Probe />, { session });
    queryClient.setQueryData(["org", ORG_A.id, "requests", "list", {}], { items: [{ id: "secret" }] });
    expect(apiAuth.get().orgId).toBe(ORG_A.id);
    expect(screen.getByTestId("org")).toHaveTextContent("Northwind");

    act(() => screen.getByText("switch").click());

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(queryClient.getQueryData(["org", ORG_A.id, "requests", "list", {}])).toBeUndefined();
    expect(apiAuth.get().orgId).toBe(ORG_B.id);
    expect(screen.getByTestId("org")).toHaveTextContent("Ala-Too");
    expect(mockRouter.push).toHaveBeenCalledWith("/dashboard");
    expect(JSON.parse(window.sessionStorage.getItem("fixflow.session")!).orgId).toBe(ORG_B.id);
  });
});

describe("RouteGuard", () => {
  it("redirects unauthenticated visitors to /login with next", () => {
    renderWithProviders(
      <RouteGuard>
        <p>secret page</p>
      </RouteGuard>,
      { session: null, route: "/queue" },
    );
    expect(screen.queryByText("secret page")).not.toBeInTheDocument();
    expect(mockRouter.replace).toHaveBeenCalledWith("/login?next=%2Fqueue");
  });

  it("shows Forbidden for the wrong role and the page for the right one", () => {
    const { unmount } = renderWithProviders(
      <RouteGuard roles={["ADMIN"]}>
        <p>admin page</p>
      </RouteGuard>,
      { session: fakeSession({ role: "REQUESTER" }) },
    );
    expect(screen.getByText("You do not have access to this page")).toBeInTheDocument();
    expect(screen.queryByText("admin page")).not.toBeInTheDocument();
    unmount();
    renderWithProviders(
      <RouteGuard roles={["ADMIN"]}>
        <p>admin page</p>
      </RouteGuard>,
      { session: fakeSession({ role: "ADMIN" }) },
    );
    expect(screen.getByText("admin page")).toBeInTheDocument();
  });

  it("sends users with several memberships and no selection to /select-org", () => {
    renderWithProviders(
      <RouteGuard>
        <p>page</p>
      </RouteGuard>,
      { session: fakeSession({ memberships: [membership("REQUESTER", ORG_A), membership("DISPATCHER", ORG_B)], orgId: null }), route: "/requests" },
    );
    expect(mockRouter.replace).toHaveBeenCalledWith(expect.stringContaining("/select-org"));
  });

  it("shows the session-expired screen after a 401 and drops cached data", async () => {
    const { queryClient } = renderWithProviders(
      <RouteGuard>
        <p>page</p>
      </RouteGuard>,
      { route: "/queue" },
    );
    queryClient.setQueryData(["org", ORG_A.id, "requests"], [1]);
    await act(async () => apiAuth.notifyUnauthorized());
    expect(screen.getByText("Your session has expired")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/login?expired=1&next=%2Fqueue");
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(apiAuth.get().token).toBeNull();
  });
});
