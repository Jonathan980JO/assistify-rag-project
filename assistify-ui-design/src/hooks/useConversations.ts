"use client";

import { useCallback, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";
import {
  clearLastActiveConversationId,
  getLastActiveConversationId,
  setLastActiveConversationId,
} from "@/src/lib/conversationStorage";
import type { ConversationDetail, ConversationMessage, ConversationSummary } from "@/src/lib/types";

export interface UiMessage {
  id: string;
  type: "user" | "assistant" | "system";
  content: string;
  language: "en" | "ar";
  tenant_id?: number;
  tenant_name?: string;
}

export function useConversations() {
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
    const data = await apiClient.get<{ conversations: ConversationSummary[] }>("/conversations");
    setConversations(data.conversations ?? []);
    return data.conversations ?? [];
  }, []);

  const loadConversation = useCallback(
    async (id: string, tenantNames?: Record<number, string>) => {
      const data = await apiClient.get<ConversationDetail>(`/conversations/${id}`);
      setActiveConversationId(id);
      setActiveTenantId(data.active_tenant_id ?? null);
      setMessages((data.messages ?? []).map((m) => mapMessage(m, tenantNames)));
      setLastActiveConversationId("user", id);
      return data;
    },
    [mapMessage],
  );

  const initialize = useCallback(async () => {
    setIsLoading(true);
    try {
      const list = await refreshConversations();
      const savedId = getLastActiveConversationId("user");
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
    async (activeTenantId?: number, tenantNames?: Record<number, string>) => {
      const body = activeTenantId != null ? { active_tenant_id: activeTenantId } : {};
      const data = await apiClient.post<ConversationDetail>("/conversations", body);
      await refreshConversations();
      setActiveConversationId(data.id);
      setActiveTenantId(data.active_tenant_id ?? activeTenantId ?? null);
      setMessages((data.messages ?? []).map((m) => mapMessage(m, tenantNames)));
      setLastActiveConversationId("user", data.id);
      return data;
    },
    [mapMessage, refreshConversations],
  );

  const renameConversation = useCallback(
    async (id: string, title: string) => {
      await apiClient.patch(`/conversations/${id}`, { title });
      await refreshConversations();
    },
    [refreshConversations],
  );

  const deleteConversation = useCallback(
    async (id: string, tenantNames?: Record<number, string>) => {
      const wasActive = activeConversationId === id;
      await apiClient.delete(`/conversations/${id}`);
      const list = await refreshConversations();
      if (wasActive) {
        if (list.length > 0) {
          await loadConversation(list[0].id, tenantNames);
        } else {
          setActiveConversationId(null);
          setActiveTenantId(null);
          setMessages([]);
          clearLastActiveConversationId("user");
        }
      }
    },
    [activeConversationId, refreshConversations, loadConversation],
  );

  const clearAllConversations = useCallback(async () => {
    await apiClient.delete("/conversations");
    setActiveConversationId(null);
    setActiveTenantId(null);
    setMessages([]);
    clearLastActiveConversationId("user");
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
      setMessages((prev) => [
        ...prev,
        mapMessage({ role, text, tenant_id: tid }, tenantNames),
      ]);
      if (persist && activeConversationId) {
        await apiClient.post(`/conversations/${activeConversationId}/message`, {
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

  const adoptConversationFromWs = useCallback(
    async (conversationId: string, tenantNames?: Record<number, string>) => {
      if (!conversationId || conversationId === activeConversationId) return;
      try {
        await loadConversation(conversationId, tenantNames);
        await refreshConversations();
      } catch {
        setActiveConversationId(conversationId);
        setLastActiveConversationId("user", conversationId);
        await refreshConversations();
      }
    },
    [activeConversationId, loadConversation, refreshConversations],
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
    adoptConversationFromWs,
  };
}
