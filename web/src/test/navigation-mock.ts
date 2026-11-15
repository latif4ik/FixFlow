import { vi } from "vitest";

/** Shared fake of next/navigation (wired in setup.ts). Inspect `mockRouter.push` etc. in tests. */
export const mockRouter = {
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
};

let pathname = "/";
let search = new URLSearchParams();

export function setMockRoute(path: string, params: Record<string, string> = {}) {
  pathname = path;
  search = new URLSearchParams(params);
}
export const getMockPathname = () => pathname;
export const getMockSearch = () => search;

export function resetNavigationMock() {
  Object.values(mockRouter).forEach((f) => f.mockReset());
  setMockRoute("/");
}
