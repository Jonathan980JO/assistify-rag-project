"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, unwrapList } from "@/src/lib/apiClient";

export interface ApiUser {
  id: number;
  username: string;
  email: string;
  role: string;
  active: boolean;
  created_at?: string;
}

export function useUsers() {
  const [users, setUsers] = useState<ApiUser[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<unknown>("/api/users");
      setUsers(unwrapList<ApiUser>(data, "users"));
    } finally {
      setLoading(false);
    }
  }, []);

  const createUser = useCallback(
    async (payload: { username: string; email: string; password: string; role: string }) => {
      await apiClient.post("/api/users/create", payload);
      await refresh();
    },
    [refresh],
  );

  const deactivate = useCallback(async (id: number) => {
    await apiClient.post(`/api/users/${id}/deactivate`);
    await refresh();
  }, [refresh]);

  const activate = useCallback(async (id: number) => {
    await apiClient.post(`/api/users/${id}/activate`);
    await refresh();
  }, [refresh]);

  const remove = useCallback(async (id: number) => {
    await apiClient.delete(`/api/users/${id}/delete`);
    await refresh();
  }, [refresh]);

  const changeRole = useCallback(async (id: number, role: string) => {
    await apiClient.post(`/api/users/${id}/change-role`, { role });
    await refresh();
  }, [refresh]);

  const updateProfile = useCallback(
    async (id: number, payload: { email?: string; full_name?: string }) => {
      await apiClient.post(`/api/users/${id}/update-profile`, payload);
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return { users, loading, refresh, createUser, deactivate, activate, remove, changeRole, updateProfile };
}
