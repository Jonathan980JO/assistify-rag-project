"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, unwrapList } from "@/src/lib/apiClient";

export interface DashboardStats {
  users: number;
  documents: number;
  openTickets: number;
  totalQueries: string;
  admins?: number;
}

export function useDashboardStats({ includeAdmins = false }: { includeAdmins?: boolean } = {}) {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const requests: Promise<unknown>[] = [
        apiClient.get<unknown>("/api/users"),
        apiClient.get<unknown[] | { files?: unknown[] }>("/api/knowledge/files"),
        apiClient.get<{ open_tickets?: number }>("/api/admin/support/summary").catch(() => ({ open_tickets: 0 })),
        apiClient.get<{ total_queries?: number }>("/api/analytics/comprehensive?days=30").catch(() => ({})),
      ];
      if (includeAdmins) {
        requests.push(apiClient.get<unknown>("/api/tenant-admins"));
      }
      const results = await Promise.all(requests);
      const usersData = results[0];
      const filesData = results[1] as unknown[] | { files?: unknown[] };
      const summary = results[2] as { open_tickets?: number };
      const analytics = results[3] as { total_queries?: number };
      const adminsData = includeAdmins ? results[4] : null;

      const fileCount = Array.isArray(filesData) ? filesData.length : filesData.files?.length ?? 0;

      setStats({
        users: unwrapList<unknown>(usersData, "users").length,
        documents: fileCount,
        openTickets: summary.open_tickets ?? 0,
        totalQueries: analytics.total_queries != null ? String(analytics.total_queries) : "—",
        admins: adminsData != null ? unwrapList<unknown>(adminsData, "admins").length : undefined,
      });
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [includeAdmins]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return { stats, loading, refresh };
}
