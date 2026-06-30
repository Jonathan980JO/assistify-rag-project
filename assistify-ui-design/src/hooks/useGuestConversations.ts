"use client";

import { useCallback, useState } from "react";
import { guestApiClient } from "@/src/lib/guestApiClient";
import {
  clearLastActiveConversationId,
  getLastActiveConversationId,
  setLastActiveConversationId,
} from "@/src/lib/conversationStorage";
import type { ConversationDetail, ConversationMessage, ConversationSummary } from "@/src/lib/types";
import type { UiMessage } from "@/src/hooks/useConversations";

const GUEST_CONV_PREFIX = "/api/guest/conversations";

export function useGuestConversations() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeTenantId, setActiveTenantId] = useState<number | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const mapMessage = useCallback((msg: ConversationMessage, tenantNames?: Record<number, string>): UiMessage => {
    const text = msg.text || msg.content || "";
    const language: "en" | "ar" = /[\u0600-\u06FF]/.test(text) ? "ar" : "en";
    const role = msg.role === "system" ? "system" : msg.role;
    const tid = msg.tenant_id;
    return {
      id: msg.id || `${Date.now()}-${Math.random()}`,
      type: role,
      content: text,
      language,
      tenant_id: tid,
      tenant_name: tid != null ? tenantNames?.[tid] : undefined,
    };
  }, []);

  const refreshConversations = useCallback(async () => {
    const data = await guestApiClient.get<{ conversations: ConversationSummary[] }>(GUEST_CONV_PREFIX);
    setConversations(data.conversations ?? []);
    return data.conversations ?? [];
  }, []);

  const loadConversation = useCallback(
    async (id: string, tenantNames?: Record<number, string>) => {
      const data = await guestApiClient.get<ConversationDetail>(`${GUEST_CONV_PREFIX}/${id}`);
      setActiveConversationId(id);
      setActiveTenantId(data.active_tenant_id ?? null);
      setMessages((data.messages ?? []).map((m) => mapMessage(m, tenantNames)));
      setLastActiveConversationId("guest", id);
      return data;
    },
    [mapMessage],
  );

  const initialize = useCallback(async () => {
    setIsLoading(true);
    try {
      const list = await refreshConversations();
      const savedId = getLastActiveConversationId("guest");
      const restoreId =
        savedId && list.some((c) => c.id === savedId) ? savedId : list[0]?.id ?? null;
      if (restoreId) {
        await loadConversation(restoreId);
      }
    } finally {
      setIsLoading(false);
    }
  }, [refreshConversations, loadConversation]);

  const createConversation = useCallback(
    async (tenantId?: number, tenantNames?: Record<number, string>) => {
      const body = tenantId != null ? { active_tenant_id: tenantId } : {};
      const data = await guestApiClient.post<ConversationDetail>(GUEST_CONV_PREFIX, body);
      await refreshConversations();
      setActiveConversationId(data.id);
      setActiveTenantId(data.active_tenant_id ?? tenantId ?? null);
      setMessages((data.messages ?? []).map((m) => mapMessage(m, tenantNames)));
      setLastActiveConversationId("guest", data.id);
      return data;
    },
    [mapMessage, refreshConversations],
  );

  const renameConversation = useCallback(
    async (id: string, title: string) => {
      await guestApiClient.patch(`${GUEST_CONV_PREFIX}/${id}`, { title });
      await refreshConversations();
    },
    [refreshConversations],
  );

  const deleteConversation = useCallback(
    async (id: string, tenantNames?: Record<number, string>) => {
      const wasActive = activeConversationId === id;
      await guestApiClient.delete(`${GUEST_CONV_PREFIX}/${id}`);
      const list = await refreshConversations();
      if (wasActive) {
        if (list.length > 0) {
          await loadConversation(list[0].id, tenantNames);
        } else {
          setActiveConversationId(null);
          setActiveTenantId(null);
          setMessages([]);
          clearLastActiveConversationId("guest");
        }
      }
    },
    [activeConversationId, refreshConversations, loadConversation],
  );

  const clearAllConversations = useCallback(async () => {
    await guestApiClient.delete(GUEST_CONV_PREFIX);
    setActiveConversationId(null);
    setActiveTenantId(null);
    setMessages([]);
    clearLastActiveConversationId("guest");
    await refreshConversations();
  }, [refreshConversations]);

  const appendMessage = useCallback(
    async (
      role: "user" | "assistant" | "system",
      text: string,
      persist = true,
      tenantId?: number,
      tenantNames?: Record<number, string>,
    ) => {
      const tid = tenantId ?? activeTenantId ?? undefined;
      setMessages((prev) => [...prev, mapMessage({ role, text, tenant_id: tid }, tenantNames)]);
      if (persist && activeConversationId) {
        await guestApiClient.post(`${GUEST_CONV_PREFIX}/${activeConversationId}/message`, {
          role,
          text,
          tenant_id: tid,
        });
        await refreshConversations();
      }
    },
    [activeConversationId, activeTenantId, mapMessage, refreshConversations],
  );

  const reloadActiveConversation = useCallback(
    async (tenantNames?: Record<number, string>) => {
      if (!activeConversationId) return;
      await loadConversation(activeConversationId, tenantNames);
    },
    [activeConversationId, loadConversation],
  );

  return {
    conversations,
    activeConversationId,
    activeTenantId,
    setActiveTenantId,
    messages,
    isLoading,
    initialize,
    loadConversation,
    createConversation,
    renameConversation,
    deleteConversation,
    clearAllConversations,
    appendMessage,
    reloadActiveConversation,
  };
}
