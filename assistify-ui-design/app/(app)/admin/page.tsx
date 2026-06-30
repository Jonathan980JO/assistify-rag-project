"use client";

import { RoleDashboard } from "@/src/components/RoleDashboard";
import { useDashboardStats } from "@/src/hooks/useDashboardStats";

export default function AdminDashboardPage() {
  const { stats, loading } = useDashboardStats();
  const links = [
    ["Users", "/admin/users"],
    ["Knowledge", "/admin/knowledge"],
    ["Analytics", "/admin/analytics"],
    ["Audit Logs", "/admin/audit-logs"],
    ["Access Requests", "/admin/access-requests"],
    ["Tickets", "/admin/tickets"],
  ] as const;

  return (
    <RoleDashboard
      title="Admin Dashboard"
      subtitle="Welcome back! Manage your Assistify workspace."
      links={links}
      stats={[
        { label: "Users", value: loading ? "—" : String(stats?.users ?? 0), iconKey: "Users", colorClass: "text-[#2563eb]" },
        { label: "Documents", value: loading ? "—" : String(stats?.documents ?? 0), iconKey: "Knowledge", colorClass: "text-[#f6c33c]" },
        { label: "Open Tickets", value: loading ? "—" : String(stats?.openTickets ?? 0), iconKey: "Tickets", colorClass: "text-[#6c63ff]" },
        { label: "Total Queries", value: loading ? "—" : stats?.totalQueries ?? "—", iconKey: "Analytics", colorClass: "text-[#10a37f]" },
      ]}
    />
  );
}
