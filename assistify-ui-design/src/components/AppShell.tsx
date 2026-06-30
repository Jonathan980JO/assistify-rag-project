"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  Bell,
  BookOpen,
  Building2,
  Clipboard,
  LayoutDashboard,
  Lock,
  Menu,
  MessageSquare,
  Settings,
  Shield,
  Ticket,
  Users,
  X,
} from "lucide-react";
import { LogoutLink } from "@/src/components/ui/LogoutLink";
import { useProfile } from "@/src/hooks/useProfile";
import { useRoleNav } from "@/src/hooks/useRoleNav";
import { useSessionHeartbeat } from "@/src/hooks/useSessionHeartbeat";
import { appPath } from "@/src/lib/routes";

const ICON_BY_LABEL: Record<string, React.ComponentType<{ className?: string }>> = {
  Dashboard: LayoutDashboard,
  Overview: LayoutDashboard,
  Superadmin: Shield,
  Users: Users,
  Analytics: BarChart3,
  "Audit Logs": Clipboard,
  "Access Requests": Lock,
  Knowledge: BookOpen,
  "Knowledge Base": BookOpen,
  Tickets: Ticket,
  "Support Tickets": Ticket,
  Notifications: Bell,
  Profile: Settings,
  "Manage Admins": Shield,
  Customers: Users,
  Chat: MessageSquare,
  "My Tickets": Ticket,
  Businesses: Building2,
};

function navIcon(label: string) {
  const Icon = ICON_BY_LABEL[label] ?? LayoutDashboard;
  return <Icon className="h-5 w-5" />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { profile } = useProfile();
  const { sideLinks, homeHref } = useRoleNav();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const showSide = sideLinks.length > 0;

  useEffect(() => {
    if (window.matchMedia("(min-width: 1024px)").matches) {
      setSidebarOpen(true);
    }
  }, []);

  const closeSidebarIfMobile = () => {
    if (window.matchMedia("(max-width: 1023px)").matches) {
      setSidebarOpen(false);
    }
  };

  // Keep an actively-used admin session from silently idle-expiring mid-task
  // (which would turn the next request into a 401 + forced logout).
  useSessionHeartbeat({ enabled: Boolean(profile) });

  const isActive = (href: string) => {
    if (href === "/logout") return false;
    const path = href.replace(/\/$/, "");
    const current = (pathname ?? "").replace(/\/$/, "");
    return current === path || current.startsWith(`${path}/`);
  };

  const displayName = profile?.full_name || profile?.username || "User";
  const roleLabel = profile?.role?.replace(/_/g, " ") ?? "";
  const businessLabel = profile?.tenant_name || (profile?.tenant_id ? `Business #${profile.tenant_id}` : "");

  return (
    <div className="flex h-[100dvh] bg-[#232323] text-[#fafaff]">
      {showSide && sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close navigation menu"
        />
      )}

      {showSide && (
        <div
          className={`fixed inset-y-0 left-0 z-50 flex w-[min(100vw-3rem,16rem)] flex-col overflow-hidden border-r border-[#333333] bg-[#171717] transition-[transform,width] duration-300 lg:static lg:z-auto lg:w-64 ${
            sidebarOpen
              ? "translate-x-0"
              : "-translate-x-full lg:translate-x-0 lg:w-0 lg:border-r-0"
          }`}
        >
          <div className="border-b border-[#333333] p-4 lg:p-6">
            <Link href={homeHref} className="flex items-center gap-2" onClick={closeSidebarIfMobile}>
              <MessageSquare className="h-6 w-6 shrink-0 text-[#10a37f]" />
              <span className="text-xl font-bold text-[#10a37f]">Assistify</span>
            </Link>
          </div>

          <nav className="flex-1 space-y-1 overflow-y-auto p-3 lg:space-y-2 lg:p-4">
            {sideLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={closeSidebarIfMobile}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors lg:px-4 lg:py-3 ${
                  isActive(link.href)
                    ? "bg-[#10a37f] text-white"
                    : "text-[#9ca3af] hover:bg-[#2b2b2b] hover:text-[#fafaff]"
                }`}
              >
                {navIcon(link.label)}
                <span className="truncate">{link.label}</span>
              </Link>
            ))}
          </nav>

          <div className="border-t border-[#333333] p-3 lg:p-4">
            <LogoutLink />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b border-[#333333] bg-[#2b2b2b] px-3 py-3 sm:gap-3 sm:px-6 sm:py-4">
          {showSide && (
            <button
              type="button"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="shrink-0 rounded-lg p-2 text-[#9ca3af] transition-colors hover:bg-[#444444]"
              aria-label={sidebarOpen ? "Close navigation menu" : "Open navigation menu"}
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          )}

          <div className="ml-auto flex min-w-0 items-center gap-2 sm:gap-4">
            <Link
              href={appPath("/")}
              className="shrink-0 rounded-lg bg-[#10a37f] px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-[#0d8a6b] sm:px-4 sm:text-sm"
            >
              <span className="sm:hidden">Chat</span>
              <span className="hidden sm:inline">Open Chat</span>
            </Link>
            <div className="hidden min-w-0 text-right sm:block">
              <p className="truncate text-sm font-medium text-[#fafaff]">{displayName}</p>
              <p className="truncate text-xs capitalize text-[#9ca3af]">{roleLabel}</p>
              {businessLabel ? (
                <p className="truncate text-xs text-[#10a37f]">{businessLabel}</p>
              ) : null}
            </div>
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#10a37f] to-[#2563eb] text-sm font-bold text-white sm:h-10 sm:w-10"
              title={displayName}
            >
              {displayName.charAt(0).toUpperCase()}
            </div>
          </div>
        </div>

        <main className="flex-1 overflow-y-auto overflow-x-hidden bg-[#232323] p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
