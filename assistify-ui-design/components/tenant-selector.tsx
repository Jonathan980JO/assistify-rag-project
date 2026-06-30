"use client";

import { Building2, Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ChatTenant } from "@/src/lib/types";

type TenantSelectorProps = {
  tenants: ChatTenant[];
  activeTenantId: number;
  onChange: (tenantId: number) => void;
  disabled?: boolean;
};

export function TenantSelector({ tenants, activeTenantId, onChange, disabled }: TenantSelectorProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const activeTenant = tenants.find((t) => t.id === activeTenantId) ?? tenants[0];
  const isDisabled = disabled || tenants.length === 0;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const selectTenant = (tenantId: number) => {
    if (tenantId !== activeTenantId) onChange(tenantId);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        disabled={isDisabled}
        onClick={() => !isDisabled && setOpen((v) => !v)}
        className="flex h-9 min-w-[9.5rem] max-w-[min(14rem,42vw)] items-center gap-1.5 rounded-lg border border-[#444] bg-[#333] px-2.5 text-left text-sm text-[#e8e8e8] transition-colors hover:bg-[#3a3a3a] hover:border-[#555] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#10a37f]/60"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={
          activeTenant
            ? `Knowledge base: ${activeTenant.name}. Click to change.`
            : "Select knowledge base"
        }
        title={activeTenant?.name ?? "Select tenant"}
      >
        <Building2 className="h-3.5 w-3.5 shrink-0 text-[#10a37f]" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-medium">{activeTenant?.name ?? "Tenant"}</span>
        <ChevronDown
          className={`ml-auto h-3.5 w-3.5 shrink-0 text-[#9ca3af] transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      {open && tenants.length > 0 && (
        <div
          role="listbox"
          aria-label="Knowledge bases"
          className="absolute bottom-full left-0 z-[60] mb-2 max-h-64 min-w-full w-max max-w-[min(16rem,90vw)] overflow-y-auto rounded-xl border border-[#444] bg-[#2b2b2b] py-1 shadow-xl"
        >
          <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#6b7280]">
            Knowledge base
          </p>
          {tenants.map((tenant) => {
            const selected = tenant.id === activeTenantId;
            return (
              <button
                key={tenant.id}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => selectTenant(tenant.id)}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
                  selected
                    ? "bg-[#10a37f]/15 text-[#10a37f]"
                    : "text-[#e5e5e5] hover:bg-[#333]"
                }`}
              >
                <span className="flex-1 truncate">{tenant.name}</span>
                {selected && <Check className="h-4 w-4 shrink-0" aria-hidden />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
