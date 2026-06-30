"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";
import type { ChatTenant } from "@/src/lib/types";

const AUTH_LAST_TENANT_KEY = "assistify_last_chat_tenant_id";
const GUEST_LAST_TENANT_KEY = "assistify_guest_last_chat_tenant_id";

export function getLastUsedTenantId(mode: "auth" | "guest" = "auth"): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(mode === "guest" ? GUEST_LAST_TENANT_KEY : AUTH_LAST_TENANT_KEY);
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function setLastUsedTenantId(tenantId: number, mode: "auth" | "guest" = "auth") {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    mode === "guest" ? GUEST_LAST_TENANT_KEY : AUTH_LAST_TENANT_KEY,
    String(tenantId),
  );
}

export function useChatTenants() {
  const [tenants, setTenants] = useState<ChatTenant[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<{ tenants: ChatTenant[] }>("/api/chat-tenants");
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
