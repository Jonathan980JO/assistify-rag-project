"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, unwrapList } from "@/src/lib/apiClient";

export interface CustomerRow {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  active: boolean;
}

export interface CustomerNote {
  id: number;
  text: string;
  created_at: string;
  author?: string;
}

export function useCustomers() {
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<unknown>("/api/customers");
      setCustomers(unwrapList<CustomerRow>(data, "customers"));
    } finally {
      setLoading(false);
    }
  }, []);

  const updateProfile = useCallback(
    async (id: number, payload: Record<string, unknown>) => {
      await apiClient.post(`/api/users/${id}/update-profile`, payload);
      await refresh();
    },
    [refresh],
  );

  const activate = useCallback(
    async (id: number) => {
      await apiClient.post(`/api/customers/${id}/activate`, {});
      await refresh();
    },
    [refresh],
  );

  const deactivate = useCallback(
    async (id: number) => {
      await apiClient.post(`/api/customers/${id}/deactivate`, {});
      await refresh();
    },
    [refresh],
  );

  const triggerPasswordReset = useCallback(async (id: number) => {
    await apiClient.post(`/api/customers/${id}/trigger-password-reset`, {});
  }, []);

  const getNotes = useCallback(async (id: number) => {
    return apiClient.get<{ notes: CustomerNote[] }>(`/api/customers/${id}/notes`);
  }, []);

  const addNote = useCallback(async (id: number, text: string) => {
    await apiClient.post(`/api/customers/${id}/notes`, { text });
  }, []);

  const deleteNote = useCallback(async (customerId: number, noteId: number) => {
    await apiClient.delete(`/api/customers/${customerId}/notes/${noteId}`);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return {
    customers,
    loading,
    refresh,
    updateProfile,
    activate,
    deactivate,
    triggerPasswordReset,
    getNotes,
    addNote,
    deleteNote,
  };
}
