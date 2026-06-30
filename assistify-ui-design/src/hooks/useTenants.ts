"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";

export interface TenantUser {
  id: number;
  username: string;
  email?: string;
  full_name?: string;
  active: boolean;
}

export interface Tenant {
  id: number;
  name: string;
  slug?: string;
  active: boolean;
  created_at?: string;
  plan?: string;
  allow_multiple_admins?: boolean;
  admin_count?: number;
  user_count?: number;
  role_counts?: Record<string, number>;
  membership_stats?: Record<string, number>;
  master_admins?: TenantUser[];
  admins?: TenantUser[];
  employees?: TenantUser[];
  membership_customers?: TenantUser[];
}

export function slugFromName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

function parseTenantsResponse(data: Tenant[] | { tenants: Tenant[] }): Tenant[] {
  return Array.isArray(data) ? data : data.tenants ?? [];
}

export function useTenants() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<Tenant[] | { tenants: Tenant[] }>("/api/tenants");
      setTenants(parseTenantsResponse(data));
    } finally {
      setLoading(false);
    }
  }, []);

  const createTenant = useCallback(
    async (payload: { name: string; slug: string; plan?: string }) => {
      await apiClient.post("/api/tenants/create", {
        name: payload.name.trim(),
        slug: payload.slug.trim().toLowerCase(),
        plan: payload.plan ?? "standard",
      });
      await refresh();
    },
    [refresh],
  );

  const activate = useCallback(
    async (id: number) => {
      await apiClient.post(`/api/tenants/${id}/activate`, {});
      await refresh();
    },
    [refresh],
  );

  const deactivate = useCallback(
    async (id: number) => {
      await apiClient.post(`/api/tenants/${id}/deactivate`, {});
      await refresh();
    },
    [refresh],
  );

  const createManager = useCallback(
    async (
      tenantId: number,
      payload: { username: string; password: string; email?: string; full_name?: string },
    ) => {
      await apiClient.post(`/api/tenants/${tenantId}/managers`, payload);
      await refresh();
    },
    [refresh],
  );

  const updateManager = useCallback(
    async (
      tenantId: number,
      userId: number,
      payload: { email?: string; full_name?: string; password?: string; active?: boolean },
    ) => {
      await apiClient.patch(`/api/tenants/${tenantId}/managers/${userId}`, payload);
      await refresh();
    },
    [refresh],
  );

  const deleteManager = useCallback(
    async (tenantId: number, userId: number) => {
      await apiClient.delete(`/api/tenants/${tenantId}/managers/${userId}`);
      await refresh();
    },
    [refresh],
  );

  const updateSettings = useCallback(
    async (tenantId: number, allowMultipleAdmins: boolean) => {
      await apiClient.post(`/api/tenants/${tenantId}/settings`, {
        allow_multiple_admins: allowMultipleAdmins,
      });
      await refresh();
    },
    [refresh],
  );

  const deleteTenant = useCallback(
    async (id: number, confirmSlug: string) => {
      await apiClient.delete(`/api/tenants/${id}`, { confirm_slug: confirmSlug });
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return {
    tenants,
    loading,
    refresh,
    createTenant,
    activate,
    deactivate,
    createManager,
    updateManager,
    deleteManager,
    updateSettings,
    deleteTenant,
  };
}
