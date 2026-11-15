import { cva } from "class-variance-authority";
import type { VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export const buttonStyles = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-55",
  {
    variants: {
      variant: {
        primary: "bg-primary text-white hover:bg-primary-dark",
        secondary: "border border-border-strong bg-surface text-ink hover:bg-canvas",
        ghost: "text-text hover:bg-canvas-2",
        danger: "bg-danger text-white hover:bg-danger-dark",
      },
      size: {
        sm: "h-8 rounded-sm px-3 text-[13px]",
        md: "h-10 rounded-md px-4 text-sm",
        lg: "h-11 rounded-md px-5 text-[15px]",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonStyles> {
  /** Shows a spinner, sets aria-busy and blocks clicks (duplicate-submit protection). */
  loading?: boolean;
}

export function Button({ className, variant, size, loading, disabled, children, type = "button", ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(buttonStyles({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export interface IconButtonProps extends Omit<ButtonProps, "children" | "aria-label"> {
  "aria-label": string;
  icon: React.ReactNode;
}

export function IconButton({ icon, className, size = "md", ...props }: IconButtonProps) {
  return (
    <Button
      size={size}
      variant={props.variant ?? "ghost"}
      className={cn("px-0", size === "sm" ? "w-8" : size === "lg" ? "w-11" : "w-10", className)}
      {...props}
    >
      {icon}
    </Button>
  );
}
