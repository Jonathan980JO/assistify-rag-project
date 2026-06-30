"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";

export interface Membership {
  tenant_id: number;
  business_name: string;
  status: string;
  role?: string;
}

export function useMemberships() {
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [businesses, setBusinesses] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [m, b] = await Promise.all([
        apiClient.get<{ memberships: Membership[] }>("/api/my-memberships"),
        apiClient.get<{ businesses: { id: number; name: string }[] }>("/api/businesses"),
      ]);
      setMemberships(m.memberships ?? []);
      setBusinesses(b.businesses ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  const requestAccess = useCallback(async (tenantId: number) => {
    await apiClient.post("/api/access-requests", { tenant_id: tenantId });
    await refresh();
  }, [refresh]);

  const setActiveTenant = useCallback(async (tenantId: number) => {
    await apiClient.post("/api/session/active-tenant", { tenant_id: tenantId });
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return { memberships, businesses, loading, refresh, requestAccess, setActiveTenant };
}
