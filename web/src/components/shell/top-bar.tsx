"use client";

import { Check, ChevronDown, LogOut, Menu, Wrench } from "lucide-react";
import { Dialog as RDialog } from "radix-ui";
import Link from "next/link";
import { useState } from "react";
import { Avatar, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger, IconButton } from "@/components/ui";
import { useAuth } from "@/lib/auth/auth-context";
import { cn } from "@/lib/cn";
import { useLiveStatus } from "@/lib/live";
import { ROLE_HOME, ROLE_LABEL } from "@/lib/nav";
import { NavLinks } from "./nav-links";
import { NotificationBell } from "./notification-bell";

function LiveIndicator() {
  const status = useLiveStatus();
  const label = status === "live" ? "Live" : status === "reconnecting" ? "Reconnecting" : "Offline";
  return (
    <p role="status" className="hidden items-center gap-2 whitespace-nowrap text-[13px] font-semibold text-muted 2xl:flex" aria-label={`Updates: ${label}`}>
      <span
        aria-hidden
        className={cn("size-2 rounded-pill", status === "live" ? "bg-primary" : status === "reconnecting" ? "animate-pulse bg-warning" : "bg-danger")}
      />
      {label}
    </p>
  );
}

function OrgSwitcher() {
  const { memberships, membership, orgId, switchOrg } = useAuth();
  if (!membership) return null;
  const many = memberships.length > 1;
  const trigger = (
    <button
      type="button"
      className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-left hover:bg-canvas"
      aria-label={many ? `Organization: ${membership.organization.name}, ${ROLE_LABEL[membership.role]}. Switch organization` : undefined}
      disabled={!many}
    >
      <span className="leading-tight">
        <span className="block max-w-40 truncate text-[13px] font-bold text-ink">{membership.organization.name}</span>
        <span className="block text-xs text-muted">{ROLE_LABEL[membership.role]}</span>
      </span>
      {many && <ChevronDown className="size-4 text-muted" aria-hidden />}
    </button>
  );
  if (!many) return trigger;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>Switch organization</DropdownMenuLabel>
        {memberships.map((m) => (
          <DropdownMenuItem
            key={m.membership_id}
            onSelect={() => {
              if (m.organization.id !== orgId) switchOrg(m.organization.id);
            }}
          >
            <span className="flex-1">
              <span className="block font-semibold">{m.organization.name}</span>
              <span className="block text-xs text-muted">{ROLE_LABEL[m.role]}</span>
            </span>
            {m.organization.id === orgId && <Check className="size-4 text-primary" aria-label="Current organization" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={`Account menu for ${user.full_name}`} className="rounded-pill">
          <Avatar name={user.full_name} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <div className="px-2.5 py-2">
          <p className="text-sm font-bold text-ink">{user.full_name}</p>
          <p className="text-xs text-muted">{user.email}</p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void logout()}>
          <LogOut className="size-4" aria-hidden /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <RDialog.Root open={open} onOpenChange={setOpen}>
      <RDialog.Trigger asChild>
        <IconButton aria-label="Open menu" icon={<Menu className="size-5" aria-hidden />} className="2xl:hidden" />
      </RDialog.Trigger>
      <RDialog.Portal>
        <RDialog.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <RDialog.Content className="fixed inset-y-0 left-0 z-50 w-[min(320px,85vw)] overflow-y-auto bg-surface p-4 shadow-pop">
          <RDialog.Title className="mb-3 font-heading text-lg font-bold text-ink">Menu</RDialog.Title>
          <RDialog.Description className="sr-only">Main navigation</RDialog.Description>
          <nav aria-label="Main">
            <NavLinks orientation="vertical" onNavigate={() => setOpen(false)} withNotifications />
          </nav>
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}

export function TopBar() {
  const { role } = useAuth();
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface">
      <div className="mx-auto flex h-16 max-w-[1680px] items-center gap-2 px-4 sm:gap-3 sm:px-6">
        <MobileNav />
        <Link href={role ? ROLE_HOME[role] : "/"} className="flex items-center gap-2 rounded-md pr-2 font-heading text-lg font-extrabold text-deep">
          <span aria-hidden className="flex size-8 items-center justify-center rounded-md bg-primary text-white">
            <Wrench className="size-4" />
          </span>
          FixFlow
        </Link>
        <nav aria-label="Main" className="ml-2 hidden min-w-0 flex-1 overflow-x-auto 2xl:block">
          <NavLinks />
        </nav>
        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <LiveIndicator />
          <OrgSwitcher />
          <NotificationBell />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
