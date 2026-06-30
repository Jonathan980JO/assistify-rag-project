import { User } from "lucide-react";
import type { UiMessage } from "@/src/hooks/useConversations";
import { AssistantIcon } from "./assistant-icon";
import { MarkdownContent } from "./markdown-content";

type ChatMessageProps = {
  message: UiMessage;
  showTenantBadge?: boolean;
  isStreaming?: boolean;
};

export function ChatMessage({ message, showTenantBadge, isStreaming }: ChatMessageProps) {
  if (message.type === "system") {
    return (
      <div className="message-enter my-4 flex justify-center">
        <span className="rounded-full border border-[#404040] bg-[#2b2b2b]/80 px-4 py-1.5 text-xs text-[#9ca3af] backdrop-blur-sm">
          {message.content}
        </span>
      </div>
    );
  }

  const isUser = message.type === "user";

  return (
    <div
      className={`message-enter group mb-5 flex gap-3 ${
        isUser ? "flex-row-reverse" : "flex-row"
      }`}
    >
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl shadow-lg ${
          isUser
            ? "bg-gradient-to-br from-[#10a37f] to-[#0d8a6b] text-white"
            : "border border-[#404040] bg-gradient-to-br from-[#2f2f2f] to-[#1f1f1f] text-[#10a37f]"
        }`}
        aria-hidden
      >
        {isUser ? <User size={15} strokeWidth={2.25} /> : <AssistantIcon size={20} />}
      </div>

      <div className={`flex min-w-0 max-w-[min(85%,42rem)] flex-col ${isUser ? "items-end" : "items-start"}`}>
        {showTenantBadge && message.tenant_name && (
          <span className="mb-1.5 rounded-md bg-[#10a37f]/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[#10a37f]">
            {message.tenant_name}
          </span>
        )}

        <div
          className={`relative rounded-2xl px-4 py-3 shadow-[0_4px_24px_rgba(0,0,0,0.18)] transition-shadow group-hover:shadow-[0_6px_28px_rgba(0,0,0,0.22)] ${
            isUser
              ? "rounded-tr-md bg-gradient-to-br from-[#10a37f] to-[#0b8f6e] text-white"
              : "rounded-tl-md border border-[#3a3a3a] bg-gradient-to-br from-[#2e2e2e] to-[#262626] text-[#fafaff]"
          }`}
        >
          {!isUser && (
            <div
              className="pointer-events-none absolute inset-0 rounded-2xl rounded-tl-md opacity-[0.04]"
              style={{
                background: "linear-gradient(135deg, #10a37f 0%, transparent 50%)",
              }}
            />
          )}

          <div className="relative">
            {isUser ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
            ) : (
              <MarkdownContent
                content={message.content}
                variant="assistant"
                isStreaming={isStreaming}
              />
            )}
          </div>
        </div>

        <span className="mt-1 px-1 text-[10px] text-[#6b7280] opacity-0 transition-opacity group-hover:opacity-100">
          {isUser ? "You" : "Assistify"}
        </span>
      </div>
    </div>
  );
}
