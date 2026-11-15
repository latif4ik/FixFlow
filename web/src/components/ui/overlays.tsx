"use client";

import { X } from "lucide-react";
import { AlertDialog, Dialog as RDialog, DropdownMenu as RMenu, Popover as RPopover, Tabs as RTabs, Tooltip as RTooltip } from "radix-ui";
import { useState } from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";
import { Textarea } from "./form";

export const Popover = RPopover.Root;
export const PopoverTrigger = RPopover.Trigger;
export function PopoverContent({ className, ...props }: React.ComponentProps<typeof RPopover.Content>) {
  return (
    <RPopover.Portal>
      <RPopover.Content
        sideOffset={8}
        className={cn("z-50 rounded-lg border border-border bg-surface shadow-pop", className)}
        {...props}
      />
    </RPopover.Portal>
  );
}

/** Modal dialog. Title is required for accessibility. */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <RDialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100vw-32px)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl bg-surface p-6 shadow-pop",
            className,
          )}
        >
          <div className="flex items-start justify-between gap-4">
            <RDialog.Title className="font-heading text-lg font-bold text-ink">{title}</RDialog.Title>
            <RDialog.Close aria-label="Close" className="rounded-sm p-1 text-muted hover:bg-canvas-2">
              <X className="size-5" aria-hidden />
            </RDialog.Close>
          </div>
          {description ? (
            <RDialog.Description className="mt-1 text-sm text-muted">{description}</RDialog.Description>
          ) : (
            <RDialog.Description className="sr-only">{typeof title === "string" ? title : "Dialog"}</RDialog.Description>
          )}
          <div className="mt-4">{children}</div>
          {footer && <div className="mt-6 flex flex-wrap justify-end gap-2">{footer}</div>}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}

/**
 * Confirmation for destructive actions. With `reason`, a textarea is required (min length) and passed to onConfirm.
 * onConfirm may return a promise: the dialog shows a pending state, ignores duplicate clicks, and closes on success.
 * If it throws, the dialog stays open (the caller shows the error).
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Keep",
  destructive = true,
  reason,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  reason?: { label?: string; minLength?: number; maxLength?: number };
  onConfirm: (reason: string) => void | Promise<unknown>;
}) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const min = reason?.minLength ?? 3;
  const tooShort = Boolean(reason) && text.trim().length < min;

  async function submit() {
    if (pending || tooShort) return;
    setPending(true);
    try {
      await onConfirm(text.trim());
      onOpenChange(false);
      setText("");
    } catch {
      /* stay open so the user can retry */
    } finally {
      setPending(false);
    }
  }

  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(o) => {
        if (!pending) onOpenChange(o);
      }}
    >
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl bg-surface p-6 shadow-pop">
          <AlertDialog.Title className="font-heading text-lg font-bold text-ink">{title}</AlertDialog.Title>
          <AlertDialog.Description className="mt-1 text-sm text-muted">{description ?? "This action cannot be undone."}</AlertDialog.Description>
          {reason && (
            <div className="mt-4 flex flex-col gap-1.5">
              <label htmlFor="confirm-reason" className="text-[13px] font-semibold text-ink">
                {reason.label ?? "Reason (required)"}
              </label>
              <Textarea
                id="confirm-reason"
                value={text}
                maxLength={reason.maxLength ?? 500}
                onChange={(e) => setText(e.target.value)}
                aria-describedby="confirm-reason-hint"
              />
              <p id="confirm-reason-hint" className="text-[13px] text-muted">
                At least {min} characters.
              </p>
            </div>
          )}
          <div className="mt-6 flex flex-wrap justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <Button variant="secondary" disabled={pending}>
                {cancelLabel}
              </Button>
            </AlertDialog.Cancel>
            <Button variant={destructive ? "danger" : "primary"} loading={pending} disabled={tooShort} onClick={submit}>
              {confirmLabel}
            </Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}

export const DropdownMenu = RMenu.Root;
export const DropdownMenuTrigger = RMenu.Trigger;
export function DropdownMenuContent({ className, ...props }: React.ComponentProps<typeof RMenu.Content>) {
  return (
    <RMenu.Portal>
      <RMenu.Content
        align="end"
        sideOffset={8}
        className={cn("z-50 min-w-56 rounded-lg border border-border bg-surface p-1.5 shadow-pop", className)}
        {...props}
      />
    </RMenu.Portal>
  );
}
export function DropdownMenuItem({ className, ...props }: React.ComponentProps<typeof RMenu.Item>) {
  return (
    <RMenu.Item
      className={cn("flex cursor-pointer items-center gap-2 rounded-sm px-2.5 py-2 text-sm text-ink outline-none data-[highlighted]:bg-primary-tint", className)}
      {...props}
    />
  );
}
export const DropdownMenuLabel = ({ className, ...props }: React.ComponentProps<typeof RMenu.Label>) => (
  <RMenu.Label className={cn("px-2.5 py-1.5 text-xs font-semibold uppercase tracking-wide text-subtle", className)} {...props} />
);
export const DropdownMenuSeparator = () => <RMenu.Separator className="my-1 h-px bg-border" />;

export const Tabs = RTabs.Root;
export function TabsList({ className, ...props }: React.ComponentProps<typeof RTabs.List>) {
  return <RTabs.List className={cn("flex gap-1 overflow-x-auto border-b border-border", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof RTabs.Trigger>) {
  return (
    <RTabs.Trigger
      className={cn(
        "-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm font-semibold text-muted hover:text-ink data-[state=active]:border-primary data-[state=active]:text-ink",
        className,
      )}
      {...props}
    />
  );
}
export const TabsContent = RTabs.Content;

export const TooltipProvider = RTooltip.Provider;
export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <RTooltip.Root delayDuration={200}>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content sideOffset={6} className="z-50 rounded-sm bg-ink px-2.5 py-1.5 text-xs text-white">
          {content}
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  );
}
