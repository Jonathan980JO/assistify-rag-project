"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isRemoteVoiceSession } from "@/src/lib/networkProfile";
import type { AppLanguage } from "@/src/lib/types";

export type WsControlAction =
  | "set_language"
  | "set_conversation_id"
  | "set_active_tenant"
  | "stop_recording"
  | "clear_audio_buffer"
  | "interrupt";

type ChatWsOptions = {
  language: AppLanguage;
  conversationId: string | null;
  tenantId: number | null;
  ttsEnabled?: boolean;
  enabled?: boolean;
  wsPath?: string;
  onAssistantComplete?: (text: string) => void;
  onUserTranscript?: (text: string) => void;
  onTenantSwitched?: (payload: Record<string, unknown>) => void;
  onConversationCreated?: (conversationId: string) => void;
  onInboundMessage?: (message: Record<string, unknown>) => void;
  onBinaryMessage?: (chunk: ArrayBuffer) => void;
};

const MAX_RECONNECT_DELAY_MS = 5000;
const MAX_RECONNECT_ATTEMPTS = 12;
const REMOTE_PING_INTERVAL_MS = 20_000;

export function useChatWebSocket({
  language,
  conversationId,
  tenantId,
  ttsEnabled = true,
  enabled = true,
  wsPath = "/ws",
  onAssistantComplete,
  onUserTranscript,
  onTenantSwitched,
  onConversationCreated,
  onInboundMessage,
  onBinaryMessage,
}: ChatWsOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [kbMessage, setKbMessage] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const pendingQueueRef = useRef<string[]>([]);

  const languageRef = useRef(language);
  const conversationIdRef = useRef(conversationId);
  const tenantIdRef = useRef(tenantId);
  const ttsEnabledRef = useRef(ttsEnabled);
  const onAssistantCompleteRef = useRef(onAssistantComplete);
  const onUserTranscriptRef = useRef(onUserTranscript);
  const onTenantSwitchedRef = useRef(onTenantSwitched);
  const onConversationCreatedRef = useRef(onConversationCreated);
  const onInboundMessageRef = useRef(onInboundMessage);
  const onBinaryMessageRef = useRef(onBinaryMessage);

  useEffect(() => {
    languageRef.current = language;
    conversationIdRef.current = conversationId;
    tenantIdRef.current = tenantId;
    ttsEnabledRef.current = ttsEnabled;
    onAssistantCompleteRef.current = onAssistantComplete;
    onUserTranscriptRef.current = onUserTranscript;
    onTenantSwitchedRef.current = onTenantSwitched;
    onConversationCreatedRef.current = onConversationCreated;
    onInboundMessageRef.current = onInboundMessage;
    onBinaryMessageRef.current = onBinaryMessage;
  });

  const closedByUnmountRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPingTimer = useCallback(() => {
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const flushPendingQueue = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    while (pendingQueueRef.current.length > 0) {
      const text = pendingQueueRef.current.shift();
      if (!text) continue;
      ws.send(
        JSON.stringify({
          text,
          language: languageRef.current,
          conversation_id: conversationIdRef.current,
          tenant_id: tenantIdRef.current,
          tts_enabled: ttsEnabledRef.current,
        }),
      );
      setThinking(true);
      setStreamingText("");
    }
  }, []);

  const connect = useCallback(() => {
    if (typeof window === "undefined") return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}${wsPath}`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setConnected(true);
      setConnectionError(null);
      ws.send(JSON.stringify({ type: "control", action: "set_language", language: languageRef.current }));
      if (conversationIdRef.current) {
        ws.send(
          JSON.stringify({
            type: "control",
            action: "set_conversation_id",
            conversation_id: conversationIdRef.current,
          }),
        );
      }
      flushPendingQueue();
      clearPingTimer();
      if (isRemoteVoiceSession()) {
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, REMOTE_PING_INTERVAL_MS);
      }
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        onBinaryMessageRef.current?.(event.data);
        return;
      }
      try {
        const msg = JSON.parse(event.data as string) as Record<string, unknown>;
        onInboundMessageRef.current?.(msg);
        const type = String(msg.type ?? "");
        if (type === "thinking") setThinking(true);
        if (type === "transcript" && msg.final) {
          onUserTranscriptRef.current?.(String(msg.text ?? ""));
          setThinking(true);
        }
        if (type === "aiResponseChunk" && msg.text) {
          setStreamingText((prev) => prev + String(msg.text));
        }
        if (type === "aiResponseDone") {
          setThinking(false);
          const full = String(msg.fullText ?? "");
          setStreamingText("");
          if (full) onAssistantCompleteRef.current?.(full);
        }
        if (type === "conversation" && msg.conversation_id) {
          onConversationCreatedRef.current?.(String(msg.conversation_id));
        }
        if (type === "error" || msg.error === true) {
          setThinking(false);
          setStreamingText("");
          const errText = String(msg.message ?? msg.text ?? "Something went wrong. Please try again.");
          setLastError(errText);
        }
        if (type === "pong") {
          // keepalive ack — no UI update
        }
        if (type === "kb_updated" && msg.message) setKbMessage(String(msg.message));
        if (type === "tenant_switched") onTenantSwitchedRef.current?.(msg);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = () => {
      setConnectionError("Connection error. Retrying…");
    };

    ws.onclose = () => {
      setConnected(false);
      clearPingTimer();
      if (closedByUnmountRef.current) return;
      reconnectAttemptsRef.current += 1;
      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setConnectionError("Disconnected. Please refresh the page to reconnect.");
        return;
      }
      setConnectionError("Reconnecting…");
      const delay = Math.min(1000 * reconnectAttemptsRef.current, MAX_RECONNECT_DELAY_MS);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };
  }, [wsPath, flushPendingQueue, clearPingTimer]);

  useEffect(() => {
    if (!enabled) {
      closedByUnmountRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      clearPingTimer();
      wsRef.current?.close();
      setConnected(false);
      return;
    }
    closedByUnmountRef.current = false;
    reconnectAttemptsRef.current = 0;
    setConnectionError(null);
    connect();
    return () => {
      closedByUnmountRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      clearPingTimer();
      wsRef.current?.close();
    };
  }, [connect, enabled, clearPingTimer]);

  useEffect(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "control", action: "set_language", language }));
    ws.send(JSON.stringify({ type: "control", action: "set_conversation_id", conversation_id: conversationId }));
  }, [language, conversationId]);

  const sendText = useCallback((text: string): boolean => {
    const trimmed = text.trim();
    if (!trimmed) return false;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      pendingQueueRef.current.push(trimmed);
      setConnectionError("Not connected — message queued. Reconnecting…");
      if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setLastError("Could not send your message. Please refresh and try again.");
        return false;
      }
      return true;
    }
    ws.send(
      JSON.stringify({
        text: trimmed,
        language: languageRef.current,
        conversation_id: conversationIdRef.current,
        tenant_id: tenantIdRef.current,
        tts_enabled: ttsEnabledRef.current,
      }),
    );
    setThinking(true);
    setStreamingText("");
    setLastError(null);
    return true;
  }, []);

  const sendBinary = useCallback((buf: ArrayBuffer) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(buf);
  }, []);

  const sendControl = useCallback((action: WsControlAction, extra: Record<string, unknown> = {}) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "control", action, ...extra }));
  }, []);

  const dismissError = useCallback(() => setLastError(null), []);

  return {
    connected,
    thinking,
    streamingText,
    kbMessage,
    connectionError,
    lastError,
    sendText,
    sendBinary,
    sendControl,
    dismissKb: () => setKbMessage(null),
    dismissError,
  };
}
