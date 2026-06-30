"use client";

import { useMemo } from "react";
import { useProfile } from "@/src/hooks/useProfile";
import { homePathForRole, sideLinksForRole, topLinksForRole } from "@/src/lib/navigation";

export function useRoleNav(options: { enabled?: boolean } = {}) {
  const { profile } = useProfile(options);
  const role = profile?.role ?? "customer";

  return useMemo(
    () => ({
      role,
      homeHref: homePathForRole(role),
      topLinks: topLinksForRole(role),
      sideLinks: sideLinksForRole(role),
    }),
    [role],
  );
}
