"use client";

import Link from "next/link";
import { LayoutGrid, Menu } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRoleNav } from "@/src/hooks/useRoleNav";
import { fullAppPath } from "@/src/lib/routes";
import type { AppLanguage } from "@/src/lib/types";

export function Header({
  onMenuClick,
  language,
  onLanguageChange,
  exitUrl,
  guestMode = false,
}: {
  onMenuClick: () => void;
  language: AppLanguage;
  onLanguageChange: (l: AppLanguage) => void;
  exitUrl: string;
  guestMode?: boolean;
}) {
  const { topLinks, homeHref } = useRoleNav({ enabled: !guestMode });
  const [navOpen, setNavOpen] = useState(false);
  const navRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setNavOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  return (
    <header className="flex shrink-0 items-center gap-2 border-b border-[#333] bg-[#2b2b2b] px-3 py-2.5 md:gap-3 md:px-4 md:py-3">
      <button type="button" className="shrink-0 lg:hidden" onClick={onMenuClick} aria-label="Toggle conversations">
        <Menu className="h-5 w-5" />
      </button>
      <Link
        href={guestMode ? fullAppPath("/guest") : homeHref}
        className="truncate text-sm font-semibold text-[#10a37f] hover:text-[#0d8658] md:text-base"
      >
        Assistify Chat
      </Link>
      <div className="ml-auto flex shrink-0 items-center gap-2 md:gap-3">
        <select
          className="rounded bg-[#171717] px-2 py-1.5 text-base md:text-sm"
          value={language}
          onChange={(e) => onLanguageChange(e.target.value as AppLanguage)}
          aria-label="Language"
        >
          <option value="en">EN</option>
          <option value="ar">AR</option>
        </select>

        {guestMode ? (
          <a href={fullAppPath("/login")} className="text-sm text-[#10a37f] hover:text-[#0d8658]">
            Staff login
          </a>
        ) : (
          <div className="relative" ref={navRef}>
            <button
              type="button"
              className="rounded-lg border border-[#444] p-2 text-[#9ca3af] hover:text-white"
              onClick={() => setNavOpen((o) => !o)}
              aria-label="System navigation"
              aria-expanded={navOpen}
              aria-haspopup="true"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            {navOpen && (
              <div
                className="absolute right-0 z-50 mt-2 max-h-[70vh] w-56 overflow-y-auto rounded-lg border border-[#444] bg-[#171717] py-1 shadow-xl"
                role="menu"
              >
                {topLinks.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="block px-4 py-2 text-sm text-[#9ca3af] hover:bg-[#2b2b2b] hover:text-white"
                    role="menuitem"
                    onClick={() => setNavOpen(false)}
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}

        {!guestMode && (
          <a href={exitUrl} className="text-sm text-[#9ca3af] hover:text-white">
            Exit
          </a>
        )}
      </div>
    </header>
  );
}
