import type { FieldValues, Path, UseFormReturn } from "react-hook-form";
import { isApiError } from "@/lib/api/client";

const ALIASES: Record<string, string> = {
  preferred_window_start: "window_start",
  preferred_window_end: "window_end",
};

/**
 * Maps a 422 (`details: [{field, message}]`) onto form fields, translating API names (preferred_window_*) to form
 * names. Fields the form does not have, and non-422 errors, land in `root.server`. Returns true when handled.
 */
export function mapServerErrors<T extends FieldValues>(form: UseFormReturn<T>, error: unknown): boolean {
  if (!isApiError(error)) return false;
  const known = new Set(Object.keys(form.getValues()));
  const leftover: string[] = [];
  let applied = false;
  if (error.status === 422) {
    for (const fe of error.fieldErrors) {
      const raw = fe.field.replace(/^(body|query)\./, "");
      const name = ALIASES[raw] ?? raw;
      if (known.has(name)) {
        form.setError(name as Path<T>, { type: "server", message: fe.message });
        applied = true;
      } else {
        leftover.push(`${raw}: ${fe.message}`);
      }
    }
  }
  if (leftover.length > 0 || !applied) {
    form.setError("root.server", { type: "server", message: leftover.length ? leftover.join("; ") : error.message });
  }
  return true;
}
