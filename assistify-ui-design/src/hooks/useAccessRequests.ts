"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";

export interface AccessRequest {
  id: number;
  business_name: string;
  status: string;
  username?: string;
  created_at?: string;
}

export function useAccessRequests() {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<{ requests: AccessRequest[] }>("/api/access-requests");
      setRequests(data.requests ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  const approve = useCallback(async (id: number) => {
    await apiClient.post(`/api/access-requests/${id}/approve`);
    await refresh();
  }, [refresh]);

  const reject = useCallback(async (id: number) => {
    await apiClient.post(`/api/access-requests/${id}/reject`);
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return { requests, loading, refresh, approve, reject };
}
