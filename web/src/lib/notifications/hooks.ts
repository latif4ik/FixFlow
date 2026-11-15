"use client";

import type { NotificationOut, Page } from "@/lib/api/types";
import { useApiMutation, useApiQuery } from "@/lib/query/hooks";
import { qk } from "@/lib/query/keys";

export function useUnreadCount() {
  return useApiQuery<{ unread: number }, number>({
    queryKey: (orgId) => qk.notifications.unreadCount(orgId),
    path: "/notifications/unread-count",
    select: (d) => d.unread,
    refetchInterval: 60_000,
  });
}

export function useNotifications(params: { unread_only?: boolean; page?: number; page_size?: number } = {}) {
  return useApiQuery<Page<NotificationOut>>({
    queryKey: (orgId) => qk.notifications.list(orgId, params),
    path: "/notifications",
    query: params,
  });
}

export function useMarkNotificationRead() {
  return useApiMutation<unknown, string>({
    request: (id) => ({ path: `/notifications/${id}/read` }),
    invalidate: (orgId) => [qk.notifications.all(orgId)],
    errorMessage: "Could not mark the notification as read.",
  });
}

export function useMarkAllNotificationsRead() {
  return useApiMutation<unknown, void>({
    request: () => ({ path: "/notifications/read-all" }),
    invalidate: (orgId) => [qk.notifications.all(orgId)],
    successMessage: "All notifications marked as read.",
  });
}

/** Where a notification should take the user. */
export function notificationHref(n: NotificationOut): string | null {
  return n.request_id ? `/requests/${n.request_id}` : null;
}

