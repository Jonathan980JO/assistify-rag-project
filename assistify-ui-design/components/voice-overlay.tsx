"use client";

import { Mic, MicOff, RotateCcw, Square, X } from "lucide-react";
import type { VoiceState } from "@/src/hooks/useVoiceMode";
import { MarkdownContent } from "./markdown-content";

const STATE_COLORS: Record<VoiceState, string> = {
  idle: "from-[#6c63ff] to-[#10a37f]",
  listening: "from-[#10a37f] to-[#0d8658]",
  processing: "from-[#f59e0b] to-[#d97706]",
  transcribing: "from-[#f59e0b] to-[#d97706]",
  speaking: "from-[#6c63ff] to-[#4f46e5]",
  interrupted: "from-[#ef4444] to-[#dc2626]",
  error: "from-[#ef4444] to-[#991b1b]",
};

export function VoiceOverlay({
  isOpen,
  state,
  statusText,
  userText,
  assistantText,
  showRetry,
  onClose,
  onStop,
  onSkip,
  onRetry,
}: {
  isOpen: boolean;
  state: VoiceState;
  statusText: string;
  userText: string;
  assistantText: string;
  showRetry: boolean;
  onClose: () => void;
  onStop: () => void;
  onSkip: () => void;
  onRetry: () => void;
}) {
  if (!isOpen) return null;

  const gradient = STATE_COLORS[state] ?? STATE_COLORS.idle;
  const pulsing = state === "listening" || state === "speaking";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Voice mode"
      aria-hidden={!isOpen}
    >
      <div className="relative w-full max-w-md rounded-2xl border border-[#444] bg-[#2b2b2b] p-6 shadow-2xl">
        <button
          type="button"
          className="absolute right-4 top-4 rounded-lg p-1 text-[#9ca3af] hover:text-white"
          onClick={onClose}
          aria-label="Close voice mode"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="flex flex-col items-center gap-4 pt-2">
          <div
            className={`flex h-28 w-28 items-center justify-center rounded-full bg-gradient-to-br ${gradient} shadow-lg ${pulsing ? "animate-pulse" : ""}`}
          >
            {state === "listening" ? (
              <Mic className="h-12 w-12 text-white" />
            ) : state === "error" ? (
              <MicOff className="h-12 w-12 text-white" />
            ) : (
              <Mic className="h-12 w-12 text-white opacity-80" />
            )}
          </div>

          <p className="text-center text-sm text-[#9ca3af]">{statusText}</p>

          {userText && (
            <div className="w-full rounded-lg bg-[#171717] px-4 py-2 text-sm text-[#10a37f]">
              <span className="text-xs text-[#9ca3af]">You: </span>
              {userText}
            </div>
          )}
          {assistantText && (
            <div className="w-full rounded-lg border border-[#333] bg-[#171717] px-4 py-3 text-sm">
              <span className="mb-1 block text-xs text-[#9ca3af]">Assistify</span>
              <MarkdownContent
                content={assistantText}
                variant="assistant"
                isStreaming={state === "transcribing"}
              />
            </div>
          )}

          <div className="flex flex-wrap justify-center gap-3 pt-2">
            {state === "listening" && (
              <button
                type="button"
                className="flex items-center gap-2 rounded-lg bg-[#ef4444] px-4 py-2 text-sm font-medium text-white"
                onClick={onStop}
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            )}
            {(state === "speaking" || state === "transcribing") && (
              <button
                type="button"
                className="flex items-center gap-2 rounded-lg border border-[#444] bg-[#171717] px-4 py-2 text-sm font-medium text-[#fafaff]"
                onClick={onSkip}
              >
                Continue
              </button>
            )}
            {showRetry && (
              <button
                type="button"
                className="flex items-center gap-2 rounded-lg bg-[#10a37f] px-4 py-2 text-sm font-medium text-white"
                onClick={onRetry}
              >
                <RotateCcw className="h-4 w-4" />
                Retry
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
