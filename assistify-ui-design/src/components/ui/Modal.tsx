"use client";

import { ReactNode } from "react";
import { X } from "lucide-react";

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = "default",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: "default" | "wide";
}) {
  if (!open) return null;

  const panelClass = size === "wide" ? "max-w-5xl" : "max-w-md";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className={`w-full ${panelClass} rounded-lg border border-[#333333] bg-[#2b2b2b] p-6`}>
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-xl font-bold text-[#fafaff]">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-[#9ca3af] transition-colors hover:bg-[#333333] hover:text-[#fafaff]"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div>{children}</div>
        {footer && <div className="mt-6 flex gap-3">{footer}</div>}
      </div>
    </div>
  );
}
