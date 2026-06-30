"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { Lock } from "lucide-react";
import { appPath } from "@/src/lib/routes";

export function AuthPageShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#232323] px-4 py-12 text-[#fafaff]">
      <div className="w-full max-w-md rounded-lg border border-[#333333] bg-[#2b2b2b] p-8 shadow-xl">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-[#10a37f]">
            <Lock className="h-6 w-6 text-white" />
          </div>
          <h1 className="mb-2 text-2xl font-bold text-[#10a37f]">{title}</h1>
          {subtitle && <p className="text-sm text-[#9ca3af]">{subtitle}</p>}
        </div>
        {children}
        {footer && <div className="mt-6 text-center text-sm text-[#9ca3af]">{footer}</div>}
      </div>
    </div>
  );
}

export function AuthInput(props: React.InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }) {
  return (
    <div className="relative mb-4">
      {props.icon && <div className="absolute top-3.5 left-3 text-[#9ca3af]">{props.icon}</div>}
      <input
        {...props}
        className={`w-full rounded-lg border border-[#333333] bg-[#171717] py-3 text-[#fafaff] placeholder-[#9ca3af] transition-colors focus:border-[#10a37f] focus:outline-none ${props.icon ? "pl-10 pr-4" : "px-4"} ${props.className ?? ""}`}
      />
    </div>
  );
}

export function AuthSubmit({ label }: { label: string }) {
  return (
    <button
      type="submit"
      className="mt-2 w-full rounded-lg bg-[#10a37f] py-3 font-semibold text-white transition-colors hover:bg-[#0e9370]"
    >
      {label}
    </button>
  );
}

export function AuthError({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-6 flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
      <div className="h-2 w-2 rounded-full bg-red-500" />
      {message}
    </div>
  );
}

export function AuthSuccess({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-6 rounded-md border border-[#10a37f]/30 bg-[#10a37f]/10 p-3 text-center text-sm text-[#10a37f]">
      {message}
    </div>
  );
}

export function AuthLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-[#10a37f] transition-colors hover:text-[#0e9370]">
      {children}
    </Link>
  );
}
