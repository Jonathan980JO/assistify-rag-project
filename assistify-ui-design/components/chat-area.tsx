"use client";

import { Mic, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useChatWebSocket } from "@/src/hooks/useChatWebSocket";
import { useVoiceMode, type VoiceWsApi } from "@/src/hooks/useVoiceMode";
import type { UiMessage } from "@/src/hooks/useConversations";
import type { AppLanguage, ChatTenant } from "@/src/lib/types";
import { isRemoteVoiceSession } from "@/src/lib/networkProfile";
import { useVisualViewportInset } from "@/src/hooks/useVisualViewportInset";
import { ChatMessage } from "./chat-message";
import { AssistantIcon } from "./assistant-icon";
import { Header } from "./header";
import { KBBanner } from "./kb-banner";
import { TenantSelector } from "./tenant-selector";
import { ThinkingIndicator } from "./thinking-indicator";
import { VoiceOverlay } from "./voice-overlay";

interface ChatAreaProps {
  onMenuClick: () => void;
  messages: UiMessage[];
  activeConversationId: string | null;
  activeTenantId: number;
  appendMessage: (role: "user" | "assistant" | "system", text: string, persist?: boolean) => Promise<void>;
  onTenantSwitched?: () => void;
  onConversationCreated?: (conversationId: string) => void;
  exitUrl: string;
  wsEnabled?: boolean;
  wsPath?: string;
  guestMode?: boolean;
  tenants?: ChatTenant[];
  tenantsLoading?: boolean;
  onTenantChange?: (tenantId: number) => void;
}

export function ChatArea({
  onMenuClick,
  messages,
  activeConversationId,
  activeTenantId,
  appendMessage,
  onTenantSwitched,
  onConversationCreated,
  exitUrl,
  wsEnabled = true,
  wsPath = "/ws",
  guestMode = false,
  tenants = [],
  tenantsLoading = false,
  onTenantChange,
}: ChatAreaProps) {
  const [inputValue, setInputValue] = useState("");
  const [language, setLanguage] = useState<AppLanguage>("en");
  const useServerTts = !isRemoteVoiceSession();
  const keyboardInset = useVisualViewportInset();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const voiceOpenRef = useRef(false);
  const wsApiRef = useRef<VoiceWsApi>({
    connected: false,
    sendBinary: () => {},
    sendControl: () => {},
  });

  const persistToServer = !wsEnabled;

  const appendUser = useCallback(
    (text: string) => {
      appendMessage("user", text, persistToServer).catch(() => {});
    },
    [appendMessage, persistToServer],
  );

  const appendAssistant = useCallback(
    (text: string) => {
      appendMessage("assistant", text, persistToServer).catch(() => {});
    },
    [appendMessage, persistToServer],
  );

  const voiceMode = useVoiceMode({
    language,
    wsApiRef,
    ttsEnabled: true,
    useServerTts,
    onUserTranscript: appendUser,
    onAssistantText: () => {},
  });

  const onInboundCombined = useCallback(
    (msg: Record<string, unknown>) => {
      voiceMode.handleInboundMessage(msg);
    },
    [voiceMode],
  );

  const onBinaryCombined = useCallback(
    (chunk: ArrayBuffer) => {
      voiceMode.handleBinaryMessage(chunk);
    },
    [voiceMode],
  );

  const chatWs = useChatWebSocket({
    language,
    conversationId: activeConversationId,
    tenantId: activeTenantId,
    ttsEnabled: useServerTts,
    enabled: wsEnabled,
    wsPath,
    onAssistantComplete: appendAssistant,
    onTenantSwitched: () => onTenantSwitched?.(),
    onConversationCreated,
    onUserTranscript: (text) => {
      if (!voiceOpenRef.current) appendUser(text);
    },
    onInboundMessage: onInboundCombined,
    onBinaryMessage: onBinaryCombined,
  });

  useEffect(() => {
    wsApiRef.current = {
      connected: chatWs.connected,
      sendBinary: chatWs.sendBinary,
      sendControl: chatWs.sendControl,
    };
  }, [chatWs.connected, chatWs.sendBinary, chatWs.sendControl]);

  useEffect(() => {
    voiceOpenRef.current = voiceMode.isOpen;
  }, [voiceMode.isOpen]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, chatWs.streamingText, voiceMode.assistantText]);

  useEffect(() => {
    if (keyboardInset > 0) {
      messagesEndRef.current?.scrollIntoView({ block: "end" });
    }
  }, [keyboardInset]);

  const handleInputFocus = () => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ block: "end" });
    });
  };

  const isResponding = chatWs.thinking || Boolean(chatWs.streamingText);
  const canSend = !isResponding && Boolean(inputValue.trim());

  const handleSend = async () => {
    const text = inputValue.trim();
    if (!text || isResponding) return;
    setInputValue("");
    await appendMessage("user", text, persistToServer);
    chatWs.sendText(text);
  };

  return (
    <div className="relative flex min-h-0 flex-1 flex-col bg-[#232323]">
      <Header
        exitUrl={exitUrl}
        language={language}
        onLanguageChange={setLanguage}
        onMenuClick={onMenuClick}
        guestMode={guestMode}
      />
      {chatWs.kbMessage && <KBBanner message={chatWs.kbMessage} onDismiss={chatWs.dismissKb} />}
      {!chatWs.connected && chatWs.connectionError && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-center text-sm text-amber-200">
          {chatWs.connectionError}
        </div>
      )}
      {chatWs.lastError && (
        <div className="mx-4 mt-2 flex items-center justify-between gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          <span>{chatWs.lastError}</span>
          <button type="button" className="shrink-0 text-xs underline" onClick={chatWs.dismissError}>
            Dismiss
          </button>
        </div>
      )}
      <div
        ref={scrollContainerRef}
        className="chat-scroll-fade min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain p-3 md:p-6"
      >
        {messages.length === 0 && !chatWs.streamingText && !chatWs.thinking && (
          <div className="message-enter flex min-h-[28vh] flex-col items-center justify-center px-2 text-center md:min-h-[40vh] md:px-4">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-[#404040] bg-gradient-to-br from-[#2f2f2f] to-[#1a1a1a] p-2 shadow-[0_8px_32px_rgba(16,163,127,0.15)]">
              <AssistantIcon size={44} />
            </div>
            <h2 className="mb-2 text-xl font-semibold text-white">How can I help you today?</h2>
            <p className="max-w-md text-sm leading-relaxed text-[#9ca3af]">
              Ask questions about your knowledge base. Responses are formatted with headings, lists, and highlights for easy reading.
            </p>
          </div>
        )}
        {messages.map((m, idx) => {
          const prev = idx > 0 ? messages[idx - 1] : null;
          const showBadge =
            m.type !== "system" &&
            m.tenant_id != null &&
            (prev == null || prev.tenant_id !== m.tenant_id || prev.type === "system");
          return <ChatMessage key={m.id} message={m} showTenantBadge={showBadge} />;
        })}
        {chatWs.streamingText && !voiceMode.isOpen && (
          <ChatMessage
            message={{ id: "stream", type: "assistant", content: chatWs.streamingText, language }}
            isStreaming
          />
        )}
        {chatWs.thinking && !chatWs.streamingText && !voiceMode.isOpen && <ThinkingIndicator />}
        <div ref={messagesEndRef} />
      </div>
      <div
        className="chat-composer shrink-0 border-t border-[#333333] bg-[#232323] p-3 md:p-6"
        style={keyboardInset > 0 ? { paddingBottom: `max(0.75rem, ${keyboardInset}px)` } : undefined}
      >
        <div className="mx-auto max-w-4xl">
          <div className="rounded-2xl border border-[#404040] bg-[#2b2b2b] shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
            <input
              ref={inputRef}
              className="w-full rounded-t-2xl bg-transparent px-3 py-2.5 text-base text-[#fafaff] outline-none placeholder:text-[#9ca3af] disabled:cursor-not-allowed disabled:opacity-50 md:px-4 md:py-3 md:text-sm"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onFocus={handleInputFocus}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && !isResponding && handleSend()}
              placeholder={isResponding ? "Waiting for response..." : "Ask anything..."}
              aria-label="Message"
              disabled={isResponding}
              enterKeyHint="send"
              autoComplete="off"
            />
            <div className="flex items-center justify-between gap-2 border-t border-[#383838] px-2 py-1.5">
              <div className="min-w-0 flex-1">
                {onTenantChange && tenants.length > 0 && (
                  <TenantSelector
                    tenants={tenants}
                    activeTenantId={activeTenantId}
                    onChange={onTenantChange}
                    disabled={tenantsLoading}
                  />
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                className={`rounded-lg p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                  voiceMode.isOpen
                    ? "bg-[#6c63ff]/20 text-[#6c63ff]"
                    : "text-[#9ca3af] hover:bg-[#333333] hover:text-[#6c63ff]"
                }`}
                onClick={() => (voiceMode.isOpen ? voiceMode.closeVoiceMode() : void voiceMode.openVoiceMode())}
                disabled={(!chatWs.connected && !voiceMode.isOpen) || (isResponding && !voiceMode.isOpen)}
                title={
                  !chatWs.connected && !voiceMode.isOpen
                    ? "Waiting for connection..."
                    : isResponding && !voiceMode.isOpen
                      ? "Wait for the response to finish"
                      : undefined
                }
                aria-label={voiceMode.isOpen ? "Close voice mode" : "Open voice mode"}
              >
                <Mic size={18} />
              </button>
              <button
                type="button"
                className="rounded-lg bg-[#10a37f] p-2 text-white transition-colors hover:bg-[#0d8a6b] disabled:cursor-not-allowed disabled:opacity-40"
                onClick={handleSend}
                disabled={!canSend}
                title={isResponding ? "Wait for the response to finish" : undefined}
                aria-label="Send message"
              >
                <Send size={18} />
              </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <VoiceOverlay
        isOpen={voiceMode.isOpen}
        state={voiceMode.state}
        statusText={voiceMode.statusText}
        userText={voiceMode.userText}
        assistantText={voiceMode.assistantText}
        showRetry={voiceMode.showRetry}
        onClose={voiceMode.closeVoiceMode}
        onStop={voiceMode.stopListening}
        onSkip={voiceMode.skipSpeaking}
        onRetry={voiceMode.retry}
      />
    </div>
  );
}
