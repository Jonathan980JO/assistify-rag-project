"use client";

import { useCallback, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";
import { getLastUsedTenantId, setLastUsedTenantId } from "@/src/hooks/useChatTenants";
import type { ChatTenant } from "@/src/lib/types";

export function useActiveTenant(tenants: ChatTenant[]) {
  const defaultId = tenants[0]?.id ?? getLastUsedTenantId("auth") ?? 1;
  const [activeTenantId, setActiveTenantId] = useState<number>(defaultId);

  const resolveDefault = useCallback(() => {
    const last = getLastUsedTenantId("auth");
    if (last && tenants.some((t) => t.id === last)) {
      setActiveTenantId(last);
      return last;
    }
    if (tenants[0]) {
      setActiveTenantId(tenants[0].id);
      return tenants[0].id;
    }
    return activeTenantId;
  }, [tenants, activeTenantId]);

  const syncFromConversation = useCallback((tenantId: number | undefined) => {
    if (tenantId && tenants.some((t) => t.id === tenantId)) {
      setActiveTenantId(tenantId);
      setLastUsedTenantId(tenantId, "auth");
    }
  }, [tenants]);

  const switchTenant = useCallback(
    async (conversationId: string | null, newTenantId: number) => {
      setActiveTenantId(newTenantId);
      setLastUsedTenantId(newTenantId, "auth");
      if (conversationId) {
        await apiClient.patch(`/conversations/${conversationId}/active-tenant`, {
          active_tenant_id: newTenantId,
        });
      }
    },
    [],
  );

  const activeTenant = tenants.find((t) => t.id === activeTenantId) ?? null;

  return {
    activeTenantId,
    activeTenant,
    setActiveTenantId,
    resolveDefault,
    syncFromConversation,
    switchTenant,
  };
}
