"use client";

import { ReactNode, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useProfile } from "@/src/hooks/useProfile";
import { homePathForRole, type AppRole } from "@/src/lib/navigation";

const ROUTE_ROLE_PREFIXES: { prefix: string; roles: AppRole[] }[] = [
  { prefix: "/superadmin", roles: ["superadmin"] },
  { prefix: "/master_admin", roles: ["master_admin"] },
  { prefix: "/admin", roles: ["admin"] },
  { prefix: "/employee", roles: ["employee"] },
];

function requiredRolesForPath(pathname: string | null): AppRole[] | null {
  const current = (pathname ?? "").replace(/\/$/, "");
  for (const { prefix, roles } of ROUTE_ROLE_PREFIXES) {
    if (current === prefix || current.startsWith(`${prefix}/`)) {
      return roles;
    }
  }
  return null;
}

export function RoleGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { profile, isLoading } = useProfile();

  useEffect(() => {
    if (isLoading || !profile) return;
    const allowed = requiredRolesForPath(pathname);
    if (!allowed) return;
    if (!allowed.includes(profile.role)) {
      window.location.href = homePathForRole(profile.role);
    }
  }, [isLoading, profile, pathname]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#232323] text-[#9ca3af]">
        Loading...
      </div>
    );
  }

  const allowed = requiredRolesForPath(pathname);
  if (profile && allowed && !allowed.includes(profile.role)) {
    return null;
  }

  return <>{children}</>;
}
