import { z } from "zod";

export const TITLE_MIN = 5;
export const TITLE_MAX = 120;
export const DESC_MIN = 20;
export const DESC_MAX = 3000;
export const MAX_IMAGES = 3;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

/** Shared window refinement: all-or-nothing date/start/end and end > start. */
function windowIssues(v: { window_date?: string; window_start?: string; window_end?: string }, ctx: z.RefinementCtx) {
  const any = v.window_date || v.window_start || v.window_end;
  if (!any) return;
  if (!v.window_date) ctx.addIssue({ code: "custom", path: ["window_date"], message: "Choose a date for the preferred visit." });
  if (!v.window_start) ctx.addIssue({ code: "custom", path: ["window_start"], message: "Choose a start time." });
  if (!v.window_end) ctx.addIssue({ code: "custom", path: ["window_end"], message: "Choose an end time." });
  if (v.window_start && v.window_end && v.window_end <= v.window_start) {
    ctx.addIssue({ code: "custom", path: ["window_end"], message: "End time must be after the start time." });
  }
}

const title = z.string().trim().min(TITLE_MIN, `Title must be at least ${TITLE_MIN} characters.`).max(TITLE_MAX, `Title must be at most ${TITLE_MAX} characters.`);
const description = z
  .string()
  .trim()
  .min(DESC_MIN, `Description must be at least ${DESC_MIN} characters.`)
  .max(DESC_MAX, `Description must be at most ${DESC_MAX} characters.`);

export const newRequestSchema = z
  .object({
    title,
    description,
    category_id: z.string().min(1, "Choose a category."),
    property_id: z.string().min(1, "Choose a property."),
    asset_id: z.string().optional(),
    priority: z.enum(["LOW", "NORMAL", "HIGH"]),
    window_date: z.string().optional(),
    window_start: z.string().optional(),
    window_end: z.string().optional(),
  })
  .superRefine(windowIssues);
export type NewRequestValues = z.infer<typeof newRequestSchema>;

export const editRequestSchema = z
  .object({
    title,
    description,
    window_date: z.string().optional(),
    window_start: z.string().optional(),
    window_end: z.string().optional(),
  })
  .superRefine(windowIssues);
export type EditRequestValues = z.infer<typeof editRequestSchema>;

/** Returns an error message or null. */
export function validateImage(file: File): string | null {
  if (!(IMAGE_TYPES as readonly string[]).includes(file.type)) return `${file.name}: only JPEG, PNG or WebP images are allowed.`;
  if (file.size > MAX_IMAGE_BYTES) return `${file.name}: larger than 10 MB.`;
  if (file.size === 0) return `${file.name}: the file is empty.`;
  return null;
}
