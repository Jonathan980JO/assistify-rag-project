"use client";

import { RoleDashboard } from "@/src/components/RoleDashboard";
import { useDashboardStats } from "@/src/hooks/useDashboardStats";

export default function MasterAdminDashboardPage() {
  const { stats, loading } = useDashboardStats({ includeAdmins: true });
  const links = [
    ["Manage Admins", "/master_admin/admins"],
    ["Users", "/master_admin/users"],
    ["Knowledge", "/master_admin/knowledge"],
    ["Analytics", "/master_admin/analytics"],
    ["Audit Logs", "/master_admin/audit-logs"],
    ["Access Requests", "/master_admin/access-requests"],
    ["Tickets", "/master_admin/tickets"],
  ] as const;

  return (
    <RoleDashboard
      title="Master Admin Dashboard"
      subtitle="Manage your business workspace, team, and customer support."
      links={links}
      stats={[
        { label: "Admins", value: loading ? "—" : String(stats?.admins ?? 0), iconKey: "Manage Admins", colorClass: "text-[#2563eb]" },
        { label: "Users", value: loading ? "—" : String(stats?.users ?? 0), iconKey: "Users", colorClass: "text-[#f6c33c]" },
        { label: "Open Tickets", value: loading ? "—" : String(stats?.openTickets ?? 0), iconKey: "Tickets", colorClass: "text-[#6c63ff]" },
        { label: "Total Queries", value: loading ? "—" : stats?.totalQueries ?? "—", iconKey: "Analytics", colorClass: "text-[#10a37f]" },
      ]}
    />
  );
}
