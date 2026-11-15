"use client";

import { Bell } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button, DateTime, Popover, PopoverContent, PopoverTrigger } from "@/components/ui";
import { cn } from "@/lib/cn";
import { notificationHref, useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications, useUnreadCount } from "@/lib/notifications/hooks";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const unread = useUnreadCount().data ?? 0;
  const list = useNotifications({ page: 1, page_size: 6 });
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
          className="relative flex size-10 items-center justify-center rounded-md text-text hover:bg-canvas-2"
        >
          <Bell className="size-5" aria-hidden />
          {unread > 0 && (
            <span data-testid="unread-count" className="absolute right-0.5 top-0.5 min-w-5 rounded-pill bg-danger px-1 text-center text-[11px] font-bold leading-5 text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(380px,calc(100vw-24px))]">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="font-heading text-base font-bold text-ink">Notifications</h2>
          <Button size="sm" variant="ghost" disabled={unread === 0} loading={markAll.isPending} onClick={() => markAll.mutate()}>
            Mark all read
          </Button>
        </div>
        <ul className="max-h-96 overflow-y-auto">
          {list.isLoading && <li className="p-4 text-sm text-muted">Loading</li>}
          {list.isError && <li className="p-4 text-sm text-danger-dark">{list.error.message}</li>}
          {list.data?.items.length === 0 && <li className="p-4 text-sm text-muted">You are all caught up.</li>}
          {list.data?.items.map((n) => {
            const href = notificationHref(n);
            const body = (
              <>
                <span className="flex items-start gap-2">
                  {!n.read_at && <span aria-label="Unread" className="mt-1.5 size-2 shrink-0 rounded-pill bg-primary" />}
                  <span className={cn("text-sm text-ink", !n.read_at && "font-semibold")}>{n.title}</span>
                </span>
                <span className="mt-0.5 block text-[13px] text-muted">{n.body}</span>
                <DateTime value={n.created_at} style="short" className="text-xs text-subtle" />
              </>
            );
            return (
              <li key={n.id} className="flex items-start gap-2 border-b border-border px-4 py-3 last:border-0">
                <div className="min-w-0 flex-1">
                  {href ? (
                    <Link href={href} onClick={() => { setOpen(false); if (!n.read_at) markRead.mutate(n.id); }} className="block">
                      {body}
                    </Link>
                  ) : (
                    <div>{body}</div>
                  )}
                </div>
                {!n.read_at && (
                  <Button size="sm" variant="ghost" aria-label={`Mark "${n.title}" as read`} onClick={() => markRead.mutate(n.id)}>
                    Mark read
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
        <div className="border-t border-border px-4 py-2.5 text-right">
          <Link href="/notifications" onClick={() => setOpen(false)} className="text-sm font-semibold text-primary hover:underline">
            View all
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
