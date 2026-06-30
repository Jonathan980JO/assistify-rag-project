import { AssistantIcon } from "./assistant-icon";

export function ThinkingIndicator() {
  return (
    <div className="message-enter flex justify-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[#404040] bg-gradient-to-br from-[#2f2f2f] to-[#1f1f1f] p-1 shadow-lg">
        <AssistantIcon size={20} />
      </div>
      <div className="thinking-shimmer flex items-center gap-1.5 rounded-2xl rounded-tl-md px-4 py-3 text-sm font-medium text-[#232323] shadow-[0_4px_20px_rgba(246,195,60,0.2)]">
        <span>Thinking</span>
        <span className="dot-1 inline-block">.</span>
        <span className="dot-2 inline-block">.</span>
        <span className="dot-3 inline-block">.</span>
      </div>
    </div>
  );
}
