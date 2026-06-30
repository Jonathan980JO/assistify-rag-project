"use client";

import { useCallback, useEffect, useState } from "react";
import { guestApiClient } from "@/src/lib/guestApiClient";
import type { ChatTenant } from "@/src/lib/types";
import { getLastUsedTenantId, setLastUsedTenantId } from "@/src/hooks/useChatTenants";

export function useGuestChatTenants() {
  const [tenants, setTenants] = useState<ChatTenant[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await guestApiClient.get<{ tenants: ChatTenant[] }>("/api/public/chat-tenants");
      setTenants(data.tenants ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { tenants, loading, refresh };
}

export function useGuestActiveTenant(tenants: ChatTenant[]) {
  const defaultId = tenants[0]?.id ?? getLastUsedTenantId("guest") ?? 1;
  const [activeTenantId, setActiveTenantId] = useState<number>(defaultId);

  const resolveDefault = useCallback(() => {
    const last = getLastUsedTenantId("guest");
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
      setLastUsedTenantId(tenantId, "guest");
    }
  }, [tenants]);

  const switchTenant = useCallback(async (conversationId: string | null, newTenantId: number) => {
    setActiveTenantId(newTenantId);
    setLastUsedTenantId(newTenantId, "guest");
    if (conversationId) {
      await guestApiClient.patch(`/api/guest/conversations/${conversationId}/active-tenant`, {
        active_tenant_id: newTenantId,
      });
    }
  }, []);

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
