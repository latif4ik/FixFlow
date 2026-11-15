"use client";

import { Toaster as Sonner, toast } from "sonner";

/** Mount once (done in the root Providers). Use `toast.success/error` from here. */
export function Toaster() {
  return <Sonner position="bottom-right" richColors closeButton toastOptions={{ classNames: { toast: "font-sans" } }} />;
}

export { toast };
