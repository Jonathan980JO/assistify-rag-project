"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";
import type { NotificationItem } from "@/src/lib/types";

export function useNotifications() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<{ notifications: NotificationItem[] }>("/api/notifications");
      setItems(data.notifications ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  const markRead = useCallback(async (id: number) => {
    await apiClient.post(`/api/notifications/${id}/read`);
    await refresh();
  }, [refresh]);

  const markAllRead = useCallback(async () => {
    await apiClient.post("/api/notifications/mark-all-read");
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return { items, loading, refresh, markRead, markAllRead };
}
