"use client";

import { AlertCircle, CheckCircle2, ImagePlus, Loader2, RotateCcw, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { IMAGE_TYPES, MAX_IMAGES } from "./schema";

export type UploadState = "idle" | "uploading" | "done" | "failed";

export interface PickedImage {
  /** Stable id; also used as client_command_id so an upload retry is idempotent. */
  id: string;
  file: File;
  state: UploadState;
  error?: string;
}

function Preview({ file }: { file: File }) {
  const [src, setSrc] = useState<string | undefined>(undefined);
  useEffect(() => {
    const r = new FileReader();
    r.onload = () => setSrc(typeof r.result === "string" ? r.result : undefined);
    r.readAsDataURL(file);
    return () => {
      r.onload = null;
    };
  }, [file]);
  // eslint-disable-next-line @next/next/no-img-element -- local preview of a file the user just picked (not an API file)
  return <img src={src} alt={`Preview of ${file.name}`} className="h-24 w-full bg-canvas-2 object-cover" />;
}

/** Up to 3 intake images. Pure presentation: the parent owns the list and the upload loop. */
export function ImagePicker({
  images,
  onAdd,
  onRemove,
  onRetry,
  disabled,
  error,
}: {
  images: PickedImage[];
  onAdd: (files: File[]) => void;
  onRemove: (id: string) => void;
  onRetry?: (id: string) => void;
  disabled?: boolean;
  error?: string | null;
}) {
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const full = images.length >= MAX_IMAGES;
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="text-[13px] font-semibold text-ink">Photos (optional)</legend>
      <p id={`${inputId}-hint`} className="text-[13px] text-muted">
        Up to {MAX_IMAGES} images, JPEG, PNG or WebP, 10 MB each.
      </p>
      {images.length > 0 && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {images.map((im) => (
            <li key={im.id} className="overflow-hidden rounded-lg border border-border">
              <Preview file={im.file} />
              <div className="flex items-center justify-between gap-1 px-2 py-1.5 text-[13px]">
                <span className="min-w-0 flex-1 truncate" title={im.file.name}>
                  {im.file.name}
                </span>
                {im.state === "uploading" && (
                  <span className="inline-flex items-center gap-1 text-muted" role="status">
                    <Loader2 className="size-3.5 animate-spin" aria-hidden /> Uploading
                  </span>
                )}
                {im.state === "done" && (
                  <span className="inline-flex items-center gap-1 text-primary-dark">
                    <CheckCircle2 className="size-3.5" aria-hidden /> Uploaded
                  </span>
                )}
                {im.state === "failed" && (
                  <span className="inline-flex items-center gap-1 text-danger-dark" role="alert">
                    <AlertCircle className="size-3.5" aria-hidden /> Failed
                  </span>
                )}
                {im.state === "failed" && onRetry && (
                  <Button size="sm" variant="secondary" onClick={() => onRetry(im.id)} aria-label={`Retry upload of ${im.file.name}`}>
                    <RotateCcw className="size-3.5" aria-hidden /> Retry
                  </Button>
                )}
                {im.state === "idle" && (
                  <button
                    type="button"
                    onClick={() => onRemove(im.id)}
                    aria-label={`Remove ${im.file.name}`}
                    className="rounded-sm p-1 text-muted hover:bg-canvas-2"
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                )}
              </div>
              {im.state === "failed" && im.error && <p className="px-2 pb-1.5 text-[12px] text-danger-dark">{im.error}</p>}
            </li>
          ))}
        </ul>
      )}
      <input
        ref={input}
        id={inputId}
        type="file"
        accept={IMAGE_TYPES.join(",")}
        multiple
        className="sr-only"
        aria-label="Choose photo files"
        tabIndex={-1}
        aria-describedby={`${inputId}-hint`}
        onChange={(e) => {
          onAdd(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      <div>
        <Button variant="secondary" disabled={full || disabled} onClick={() => input.current?.click()}>
          <ImagePlus className="size-4" aria-hidden /> Add photos
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-[13px] font-medium text-danger-dark">
          {error}
        </p>
      )}
    </fieldset>
  );
}
