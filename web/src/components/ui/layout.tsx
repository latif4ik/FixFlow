"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";
import { EmptyState, ErrorState, Skeleton } from "./display";
import type { ErrorLike } from "./display";

export interface Crumb {
  label: string;
  href?: string;
}

export function PageHeader({ title, description, breadcrumb, actions, className }: { title: ReactNode; description?: ReactNode; breadcrumb?: Crumb[]; actions?: ReactNode; className?: string }) {
  return (
    <header className={cn("mb-5 flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        {breadcrumb && breadcrumb.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-1.5">
            <ol className="flex flex-wrap items-center gap-1.5 text-[13px] text-muted">
              {breadcrumb.map((c, i) => (
                <li key={`${c.label}-${i}`} className="flex items-center gap-1.5">
                  {i > 0 && <span aria-hidden>/</span>}
                  {c.href ? (
                    <Link href={c.href} className="rounded-sm hover:text-ink hover:underline">
                      {c.label}
                    </Link>
                  ) : (
                    <span aria-current="page" className="text-ink">
                      {c.label}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </nav>
        )}
        <h1 className="text-2xl font-extrabold sm:text-[28px]">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Layout wrapper for filter controls above a table/list (wraps on phones). */
export function FilterBar({ children, className, label = "Filters" }: { children: ReactNode; className?: string; label?: string }) {
  return (
    <div role="search" aria-label={label} className={cn("mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-3", className)}>
      {children}
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  className,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Pagination" className={cn("flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm text-muted", className)}>
      <p aria-live="polite">
        {from}-{to} of {total}
      </p>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Previous page">
          <ChevronLeft className="size-4" aria-hidden /> Prev
        </Button>
        <span>
          Page {page} of {pages}
        </span>
        <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPageChange(page + 1)} aria-label="Next page">
          Next <ChevronRight className="size-4" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Sort key sent to onSortChange; omit for non-sortable columns. */
  sortKey?: string;
  className?: string;
}
export interface SortState {
  key: string;
  dir: "asc" | "desc";
}

/**
 * Server-paginated table. Sorting and paging are controlled by the caller (they map to API params).
 * The table scrolls inside its own box so the page never scrolls horizontally.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  empty,
  page,
  pageSize,
  total,
  onPageChange,
  sort,
  onSortChange,
  skeletonRows = 5,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  loading?: boolean;
  error?: ErrorLike | null;
  onRetry?: () => void;
  empty?: ReactNode;
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  sort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
  skeletonRows?: number;
}) {
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  const showEmpty = !loading && rows !== undefined && rows.length === 0;
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-panel">
      <div role="region" aria-label={caption} tabIndex={0} className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-border bg-canvas text-[13px] text-muted">
              {columns.map((c) => {
                const active = sort && c.sortKey === sort.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : c.sortKey ? "none" : undefined}
                    className={cn("whitespace-nowrap px-4 py-2.5 font-semibold", c.className)}
                  >
                    {c.sortKey && onSortChange ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded-sm hover:text-ink"
                        onClick={() => onSortChange({ key: c.sortKey!, dir: active && sort.dir === "asc" ? "desc" : "asc" })}
                      >
                        {c.header}
                        {active ? sort.dir === "asc" ? <ArrowUp className="size-3.5" aria-hidden /> : <ArrowDown className="size-3.5" aria-hidden /> : <ChevronsUpDown className="size-3.5 opacity-50" aria-hidden />}
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody aria-busy={loading || undefined}>
            {loading &&
              Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={`sk-${i}`} className="border-b border-border last:border-0">
                  {columns.map((c) => (
                    <td key={c.key} className="px-4 py-3">
                      <Skeleton className="h-4 w-full max-w-40" />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading &&
              rows?.map((row) => (
                <tr key={rowKey(row)} className="border-b border-border last:border-0 hover:bg-canvas/60">
                  {columns.map((c) => (
                    <td key={c.key} className={cn("px-4 py-3 align-middle text-ink", c.className)}>
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
        {loading && <span className="sr-only" role="status">Loading</span>}
      </div>
      {showEmpty && (empty ?? <EmptyState title="Nothing here yet" />)}
      {page !== undefined && pageSize !== undefined && total !== undefined && onPageChange && !showEmpty && (
        <Pagination page={page} pageSize={pageSize} total={total} onPageChange={onPageChange} className="border-t border-border" />
      )}
    </div>
  );
}
