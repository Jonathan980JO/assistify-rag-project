"use client";

import { useEffect, useMemo, useState } from "react";
import { ChatArea } from "./chat-area";
import { Sidebar } from "./sidebar";
import { useGuestActiveTenant, useGuestChatTenants } from "@/src/hooks/useGuestChat";
import { useGuestConversations } from "@/src/hooks/useGuestConversations";

export function GuestAssistify() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { tenants, loading: tenantsLoading } = useGuestChatTenants();
  const {
    activeTenantId: selectorTenantId,
    resolveDefault,
    syncFromConversation,
    switchTenant,
  } = useGuestActiveTenant(tenants);

  const tenantNameMap = useMemo(
    () => Object.fromEntries(tenants.map((t) => [t.id, t.name])),
    [tenants],
  );

  const {
    conversations,
    activeConversationId,
    activeTenantId: convTenantId,
    setActiveTenantId: setConvTenantId,
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
  } = useGuestConversations();

  useEffect(() => {
    if (tenantsLoading || tenants.length === 0) return;
    resolveDefault();
  }, [tenantsLoading, tenants, resolveDefault]);

  useEffect(() => {
    initialize().catch(() => {});
  }, [initialize]);

  useEffect(() => {
    if (convTenantId != null) {
      syncFromConversation(convTenantId);
    }
  }, [convTenantId, syncFromConversation]);

  const effectiveTenantId = convTenantId ?? selectorTenantId;

  const handleRenameConversation = async (id: string, title: string) => {
    const nextTitle = title.trim();
    if (!nextTitle) return;
    await renameConversation(id, nextTitle.slice(0, 80));
  };

  const handleTenantChange = async (newTenantId: number) => {
    const prevId = effectiveTenantId;
    setConvTenantId(newTenantId);
    try {
      await switchTenant(activeConversationId, newTenantId);
      if (activeConversationId) {
        await reloadActiveConversation(tenantNameMap);
      }
    } catch {
      setConvTenantId(prevId);
    }
  };

  useEffect(() => {
    if (tenantsLoading || tenants.length === 0 || isLoading) return;
    if (activeConversationId) return;
    if (conversations.length > 0) return;
    createConversation(effectiveTenantId, tenantNameMap).catch(() => {});
  }, [
    tenantsLoading,
    tenants.length,
    isLoading,
    activeConversationId,
    conversations.length,
    effectiveTenantId,
    createConversation,
    tenantNameMap,
  ]);

  const appendWithTenant = (
    role: "user" | "assistant" | "system",
    text: string,
    persist = true,
  ) => appendMessage(role, text, persist, effectiveTenantId, tenantNameMap);

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-[#232323]">
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      <div
        className={`fixed inset-y-0 left-0 z-50 transition-transform duration-300 lg:static lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Sidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          onNewChat={async () => {
            await createConversation(effectiveTenantId, tenantNameMap);
            setSidebarOpen(false);
          }}
          onSelectConversation={async (id) => {
            await loadConversation(id, tenantNameMap);
            setSidebarOpen(false);
          }}
          onRenameConversation={handleRenameConversation}
          onDeleteConversation={(id) => deleteConversation(id, tenantNameMap)}
          onClearAll={clearAllConversations}
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col min-w-0">
        <ChatArea
          messages={messages}
          activeConversationId={activeConversationId}
          activeTenantId={effectiveTenantId ?? 1}
          tenants={tenants}
          tenantsLoading={tenantsLoading}
          onTenantChange={handleTenantChange}
          appendMessage={appendWithTenant}
          onTenantSwitched={() => reloadActiveConversation(tenantNameMap)}
          exitUrl="#"
          wsEnabled
          wsPath="/ws/guest"
          guestMode
          onMenuClick={() => setSidebarOpen(!sidebarOpen)}
        />
      </div>
    </div>
  );
}
