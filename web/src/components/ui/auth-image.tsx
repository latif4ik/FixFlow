"use client";

import { useEffect, useState } from "react";
import { apiBlob } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/cn";

/** Fetches a protected file with auth headers and returns an object URL (revoked on unmount / id change). */
export function useAuthObjectUrl(fileId: string | null | undefined): { url: string | null; loading: boolean; error: boolean } {
  const { orgId } = useAuth();
  const [state, setState] = useState<{ key: string; url: string | null; error: boolean } | null>(null);
  const key = fileId && orgId ? `${orgId}:${fileId}` : null;

  useEffect(() => {
    if (!key || !fileId) return;
    let revoked: string | null = null;
    let cancelled = false;
    apiBlob(`/files/${fileId}`, { orgId })
      .then((blob) => {
        if (cancelled) return;
        revoked = URL.createObjectURL(blob);
        setState({ key, url: revoked, error: false });
      })
      .catch(() => {
        if (!cancelled) setState({ key, url: null, error: true });
      });
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [key, fileId, orgId]);

  const current = state && state.key === key ? state : null;
  return { url: current?.url ?? null, loading: key !== null && current === null, error: current?.error ?? false };
}

/** <img> for /files/{id}: never use a bare src to the API (it needs Authorization + X-Org-Id). `alt` is required. */
export function AuthImage({ fileId, alt, className, onClick }: { fileId: string; alt: string; className?: string; onClick?: () => void }) {
  const { url, loading, error } = useAuthObjectUrl(fileId);
  if (error) {
    return (
      <div role="img" aria-label={`${alt} (could not be loaded)`} className={cn("flex items-center justify-center bg-canvas-2 text-xs text-muted", className)}>
        Image unavailable
      </div>
    );
  }
  if (loading || !url) return <div aria-hidden className={cn("animate-pulse bg-canvas-2", className)} />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={alt} className={className} onClick={onClick} />;
}
