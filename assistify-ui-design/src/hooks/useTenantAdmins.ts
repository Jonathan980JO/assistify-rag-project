"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, unwrapList } from "@/src/lib/apiClient";

export interface TenantAdmin {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  active: boolean;
}

export function useTenantAdmins() {
  const [admins, setAdmins] = useState<TenantAdmin[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<unknown>("/api/tenant-admins");
      setAdmins(unwrapList<TenantAdmin>(data, "admins"));
    } finally {
      setLoading(false);
    }
  }, []);

  const createAdmin = useCallback(
    async (payload: { username: string; email: string; password: string; full_name?: string }) => {
      await apiClient.post("/api/tenant-admins/create", payload);
      await refresh();
    },
    [refresh],
  );

  const updateAdmin = useCallback(async (id: number, payload: Record<string, unknown>) => {
    await apiClient.patch(`/api/tenant-admins/${id}`, payload);
    await refresh();
  }, [refresh]);

  const removeAdmin = useCallback(async (id: number) => {
    await apiClient.delete(`/api/tenant-admins/${id}`);
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return { admins, loading, refresh, createAdmin, updateAdmin, removeAdmin };
}
