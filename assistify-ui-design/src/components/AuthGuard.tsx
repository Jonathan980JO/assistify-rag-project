"use client";

import { ReactNode, useEffect } from "react";
import { useProfile } from "@/src/hooks/useProfile";
import { fullAppPath } from "@/src/lib/routes";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { profile, isLoading, error } = useProfile();

  useEffect(() => {
    if (!isLoading && (error || !profile)) {
      window.location.href = fullAppPath("/login");
    }
  }, [isLoading, error, profile]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#232323] text-[#9ca3af]">
        Loading...
      </div>
    );
  }

  if (!profile) return null;
  return <>{children}</>;
}
