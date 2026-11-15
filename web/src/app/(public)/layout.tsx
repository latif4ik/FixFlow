import type { ReactNode } from "react";

export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <main id="main" className="flex min-h-screen items-center justify-center px-4 py-10">
      {children}
    </main>
  );
}
