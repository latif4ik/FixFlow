"use client";

import { Check, ChevronDown } from "lucide-react";
import { Checkbox as RCheckbox, Label as RLabel, RadioGroup as RRadio, Select as RSelect, Switch as RSwitch } from "radix-ui";
import { cloneElement, forwardRef, isValidElement, useId } from "react";
import type { InputHTMLAttributes, ReactElement, ReactNode, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const fieldBase =
  "w-full rounded-md border bg-surface px-3 text-sm text-ink placeholder:text-subtle disabled:bg-canvas disabled:text-subtle";

export function Label({ className, ...props }: React.ComponentProps<typeof RLabel.Root>) {
  return <RLabel.Root className={cn("text-[13px] font-semibold text-ink", className)} {...props} />;
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(function Input(
  { className, invalid, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(fieldBase, "h-10", invalid ? "border-danger" : "border-border-strong", className)}
      {...props}
    />
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }>(function Textarea(
  { className, invalid, rows = 4, ...props },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(fieldBase, "py-2", invalid ? "border-danger" : "border-border-strong", className)}
      {...props}
    />
  );
});

/**
 * Native <select>: simplest to wire with react-hook-form `register`. For a custom listbox use SelectMenu.
 */
export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }>(function Select(
  { className, invalid, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(fieldBase, "h-10 appearance-none bg-no-repeat pr-8", invalid ? "border-danger" : "border-border-strong", className)}
      {...props}
    >
      {children}
    </select>
  );
});

export interface SelectMenuOption {
  value: string;
  label: string;
}
/** Radix listbox select (controlled). Radix forbids empty-string item values: use a sentinel like "all". */
export function SelectMenu({
  value,
  onValueChange,
  options,
  placeholder,
  className,
  id,
  invalid,
  "aria-label": ariaLabel,
}: {
  value: string | undefined;
  onValueChange: (v: string) => void;
  options: SelectMenuOption[];
  placeholder?: string;
  className?: string;
  id?: string;
  invalid?: boolean;
  "aria-label"?: string;
}) {
  return (
    <RSelect.Root value={value} onValueChange={onValueChange}>
      <RSelect.Trigger
        id={id}
        aria-label={ariaLabel}
        aria-invalid={invalid || undefined}
        className={cn(fieldBase, "inline-flex h-10 items-center justify-between gap-2 text-left", invalid ? "border-danger" : "border-border-strong", className)}
      >
        <RSelect.Value placeholder={placeholder} />
        <RSelect.Icon>
          <ChevronDown className="size-4 text-muted" aria-hidden />
        </RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        <RSelect.Content position="popper" sideOffset={4} className="z-50 min-w-(--radix-select-trigger-width) rounded-md border border-border bg-surface p-1 shadow-pop">
          <RSelect.Viewport>
            {options.map((o) => (
              <RSelect.Item
                key={o.value}
                value={o.value}
                className="flex cursor-pointer items-center justify-between gap-2 rounded-sm px-2.5 py-2 text-sm text-ink outline-none data-[highlighted]:bg-primary-tint"
              >
                <RSelect.ItemText>{o.label}</RSelect.ItemText>
                <RSelect.ItemIndicator>
                  <Check className="size-4 text-primary" aria-hidden />
                </RSelect.ItemIndicator>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

export function Checkbox({ className, ...props }: React.ComponentProps<typeof RCheckbox.Root>) {
  return (
    <RCheckbox.Root
      className={cn("flex size-5 shrink-0 items-center justify-center rounded-[6px] border border-border-strong bg-surface data-[state=checked]:border-primary data-[state=checked]:bg-primary", className)}
      {...props}
    >
      <RCheckbox.Indicator>
        <Check className="size-3.5 text-white" aria-hidden />
      </RCheckbox.Indicator>
    </RCheckbox.Root>
  );
}

export function Switch({ className, ...props }: React.ComponentProps<typeof RSwitch.Root>) {
  return (
    <RSwitch.Root
      className={cn("relative h-6 w-11 shrink-0 rounded-pill bg-border-strong transition-colors data-[state=checked]:bg-primary", className)}
      {...props}
    >
      <RSwitch.Thumb className="block size-5 translate-x-0.5 rounded-pill bg-white shadow transition-transform data-[state=checked]:translate-x-[22px]" />
    </RSwitch.Root>
  );
}

export function RadioGroup({ className, ...props }: React.ComponentProps<typeof RRadio.Root>) {
  return <RRadio.Root className={cn("flex flex-col gap-2", className)} {...props} />;
}

export function RadioItem({ value, label, hint, id }: { value: string; label: ReactNode; hint?: ReactNode; id?: string }) {
  const auto = useId();
  const rid = id ?? auto;
  return (
    <div className="flex items-start gap-2.5">
      <RRadio.Item
        id={rid}
        value={value}
        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-pill border border-border-strong bg-surface data-[state=checked]:border-primary"
      >
        <RRadio.Indicator className="block size-2.5 rounded-pill bg-primary" />
      </RRadio.Item>
      <label htmlFor={rid} className="text-sm text-ink">
        {label}
        {hint && <span className="block text-[13px] text-muted">{hint}</span>}
      </label>
    </div>
  );
}

/**
 * Label + control + hint + error, wired with htmlFor / aria-describedby / aria-invalid.
 * The single child must accept `id`, `aria-describedby`, `invalid` (Input, Textarea, Select all do).
 */
export function FormField({
  label,
  htmlFor,
  hint,
  error,
  required,
  children,
  className,
}: {
  label: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  children: ReactElement<{ id?: string; "aria-describedby"?: string; invalid?: boolean }>;
  className?: string;
}) {
  const auto = useId();
  const id = htmlFor ?? auto;
  const hintId = `${id}-hint`;
  const errId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errId : null].filter(Boolean).join(" ") || undefined;
  const control = isValidElement(children)
    ? cloneElement(children, { id, "aria-describedby": describedBy, invalid: Boolean(error) || undefined })
    : children;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required && (
          <span aria-hidden className="ml-0.5 text-danger">
            *
          </span>
        )}
      </Label>
      {control}
      {hint && (
        <p id={hintId} className="text-[13px] text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errId} role="alert" className="text-[13px] font-medium text-danger-dark">
          {error}
        </p>
      )}
    </div>
  );
}

/** Form-level error banner (server errors that map to no field, via applyServerErrors -> root.server). */
export function FormServerError({ form }: { form: { formState: { errors: { root?: Record<string, { message?: string }> } } } }) {
  const msg = form.formState.errors.root?.server?.message;
  if (!msg) return null;
  return (
    <p role="alert" className="rounded-md bg-danger-tint px-3 py-2 text-sm font-medium text-danger-dark">
      {msg}
    </p>
  );
}
