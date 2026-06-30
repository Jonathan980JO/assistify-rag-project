"use client";

import { useEffect } from "react";

export function Toast({
  message,
  onDismiss,
  durationMs = 3000,
  variant = "success",
}: {
  message: string;
  onDismiss: () => void;
  durationMs?: number;
  variant?: "success" | "error";
}) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, durationMs);
    return () => window.clearTimeout(timer);
  }, [onDismiss, durationMs]);

  const borderClass = variant === "error" ? "border-red-500/40" : "border-[#10a37f]/40";
  const bgClass = variant === "error" ? "bg-red-500/10" : "bg-[#1a2e28]";

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 max-w-sm rounded-lg border px-4 py-3 text-sm text-[#fafaff] shadow-lg ${borderClass} ${bgClass}`}
      role="status"
    >
      {message}
    </div>
  );
}
