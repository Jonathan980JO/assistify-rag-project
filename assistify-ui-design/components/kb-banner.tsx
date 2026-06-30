"use client";

export function KBBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="flex items-center justify-between bg-[#10a37f]/20 px-4 py-2 text-sm text-[#fafaff]">
      <span>{message}</span>
      <button type="button" onClick={onDismiss} className="text-[#9ca3af] hover:text-white">
        Dismiss
      </button>
    </div>
  );
}
