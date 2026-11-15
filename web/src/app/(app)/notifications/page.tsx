"use client";

import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button, DateTime, EmptyState, ErrorState, FilterBar, LoadingState, PageHeader, Pagination, Panel, Switch, Label, Badge } from "@/components/ui";
import { notificationHref, useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications, useUnreadCount } from "@/lib/notifications/hooks";

const PAGE_SIZE = 20;

// Owner: W1 (shared). Fully built.
export default function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [page, setPage] = useState(1);
  const list = useNotifications({ unread_only: unreadOnly, page, page_size: PAGE_SIZE });
  const unread = useUnreadCount().data ?? 0;
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  return (
    <>
      <PageHeader
        title="Notifications"
        description={unread > 0 ? `${unread} unread` : "You are all caught up"}
        actions={
          <Button variant="secondary" disabled={unread === 0} loading={markAll.isPending} onClick={() => markAll.mutate()}>
            <CheckCheck className="size-4" aria-hidden /> Mark all read
          </Button>
        }
      />
      <FilterBar label="Notification filters">
        <div className="flex items-center gap-2">
          <Switch
            id="unread-only"
            checked={unreadOnly}
            onCheckedChange={(v) => {
              setUnreadOnly(v);
              setPage(1);
            }}
          />
          <Label htmlFor="unread-only">Unread only</Label>
        </div>
      </FilterBar>
      <Panel bodyClassName="p-0">
        {list.isLoading && <LoadingState />}
        {list.isError && <ErrorState error={{ message: list.error.message, requestId: list.error.requestId }} onRetry={() => void list.refetch()} />}
        {list.data && list.data.items.length === 0 && (
          <EmptyState icon={Bell} title={unreadOnly ? "No unread notifications" : "No notifications yet"} description="Updates about your requests appear here." />
        )}
        {list.data && list.data.items.length > 0 && (
          <ul>
            {list.data.items.map((n) => {
              const href = notificationHref(n);
              return (
                <li key={n.id} className="flex flex-wrap items-start gap-3 border-b border-border px-5 py-4 last:border-0">
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
                      <span className={n.read_at ? "" : "font-bold"}>{n.title}</span>
                      {!n.read_at && <Badge tone="primary">Unread</Badge>}
                    </p>
                    <p className="mt-0.5 text-sm text-muted">{n.body}</p>
                    <p className="mt-1 flex items-center gap-3 text-xs text-subtle">
                      <DateTime value={n.created_at} />
                      {href && (
                        <Link href={href} className="font-semibold text-primary hover:underline">
                          Open request
                        </Link>
                      )}
                    </p>
                  </div>
                  {!n.read_at && (
                    <Button size="sm" variant="secondary" aria-label={`Mark "${n.title}" as read`} loading={markRead.isPending && markRead.variables === n.id} onClick={() => markRead.mutate(n.id)}>
                      Mark read
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {list.data && list.data.total > PAGE_SIZE && <Pagination page={page} pageSize={PAGE_SIZE} total={list.data.total} onPageChange={setPage} className="border-t border-border" />}
      </Panel>
    </>
  );
}
