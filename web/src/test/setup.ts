import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { apiAuth } from "@/lib/api/session-store";
import { getMockPathname, getMockSearch, mockRouter, resetNavigationMock } from "./navigation-mock";
import { server } from "./server";

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
  usePathname: () => getMockPathname(),
  useSearchParams: () => getMockSearch(),
  useParams: () => ({}),
  redirect: vi.fn(),
  notFound: vi.fn(),
}));

class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => {};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  apiAuth.clear();
  apiAuth.setUnauthorizedHandler(null);
  window.sessionStorage.clear();
  resetNavigationMock();
});
afterAll(() => server.close());
