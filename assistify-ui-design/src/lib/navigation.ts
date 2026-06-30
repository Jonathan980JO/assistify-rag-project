import { appPath, fullAppPath } from "./routes";

export type AppRole =
  | "superadmin"
  | "master_admin"
  | "admin"
  | "employee"
  | "customer";

export interface NavLink {
  href: string;
  label: string;
}

const HOME_BY_ROLE: Record<AppRole, string> = {
  superadmin: "/superadmin",
  master_admin: "/master_admin",
  admin: "/admin",
  employee: "/employee",
  customer: "/main",
};

const TOP_LINKS_BY_ROLE: Record<AppRole, NavLink[]> = {
  superadmin: [
    { href: appPath("/superadmin"), label: "Superadmin" },
    { href: appPath("/profile"), label: "Profile" },
    { href: appPath("/notifications"), label: "Notifications" },
  ],
  master_admin: [
    { href: appPath("/master_admin"), label: "Dashboard" },
    { href: appPath("/master_admin/admins"), label: "Manage Admins" },
    { href: appPath("/master_admin/users"), label: "Users" },
    { href: appPath("/master_admin/knowledge"), label: "Knowledge" },
    { href: appPath("/master_admin/analytics"), label: "Analytics" },
    { href: appPath("/master_admin/audit-logs"), label: "Audit Logs" },
    { href: appPath("/master_admin/access-requests"), label: "Access Requests" },
    { href: appPath("/master_admin/tickets"), label: "Tickets" },
    { href: appPath("/profile"), label: "Profile" },
    { href: appPath("/notifications"), label: "Notifications" },
  ],
  admin: [
    { href: appPath("/admin"), label: "Dashboard" },
    { href: appPath("/admin/users"), label: "Users" },
    { href: appPath("/admin/knowledge"), label: "Knowledge" },
    { href: appPath("/admin/analytics"), label: "Analytics" },
    { href: appPath("/admin/audit-logs"), label: "Audit Logs" },
    { href: appPath("/admin/access-requests"), label: "Access Requests" },
    { href: appPath("/admin/tickets"), label: "Tickets" },
    { href: appPath("/profile"), label: "Profile" },
    { href: appPath("/notifications"), label: "Notifications" },
  ],
  employee: [
    { href: appPath("/employee"), label: "Dashboard" },
    { href: appPath("/employee/customers"), label: "Customers" },
    { href: appPath("/employee/tickets"), label: "Tickets" },
    { href: appPath("/profile"), label: "Profile" },
    { href: appPath("/notifications"), label: "Notifications" },
  ],
  customer: [
    { href: appPath("/main"), label: "Chat" },
    { href: appPath("/my-tickets"), label: "My Tickets" },
    { href: appPath("/select-business"), label: "Businesses" },
    { href: appPath("/profile"), label: "Profile" },
    { href: appPath("/notifications"), label: "Notifications" },
  ],
};

const SIDE_LINKS_BY_ROLE: Partial<Record<AppRole, NavLink[]>> = {
  superadmin: [
    { href: appPath("/superadmin"), label: "Businesses" },
    { href: appPath("/profile"), label: "Profile" },
    { href: appPath("/notifications"), label: "Notifications" },
  ],
  master_admin: [
    { href: appPath("/master_admin"), label: "Overview" },
    { href: appPath("/master_admin/admins"), label: "Manage Admins" },
    { href: appPath("/master_admin/users"), label: "Users" },
    { href: appPath("/master_admin/knowledge"), label: "Knowledge Base" },
    { href: appPath("/master_admin/analytics"), label: "Analytics" },
    { href: appPath("/master_admin/audit-logs"), label: "Audit Logs" },
    { href: appPath("/master_admin/access-requests"), label: "Access Requests" },
    { href: appPath("/master_admin/tickets"), label: "Support Tickets" },
  ],
  admin: [
    { href: appPath("/admin"), label: "Overview" },
    { href: appPath("/admin/users"), label: "Users" },
    { href: appPath("/admin/knowledge"), label: "Knowledge Base" },
    { href: appPath("/admin/analytics"), label: "Analytics" },
    { href: appPath("/admin/audit-logs"), label: "Audit Logs" },
    { href: appPath("/admin/access-requests"), label: "Access Requests" },
    { href: appPath("/admin/tickets"), label: "Support Tickets" },
  ],
  employee: [
    { href: appPath("/employee"), label: "Overview" },
    { href: appPath("/employee/customers"), label: "Customers" },
    { href: appPath("/employee/tickets"), label: "Support Tickets" },
  ],
  customer: [
    { href: appPath("/main"), label: "Chat" },
    { href: appPath("/my-tickets"), label: "My Tickets" },
    { href: appPath("/select-business"), label: "Businesses" },
    { href: appPath("/profile"), label: "Profile" },
    { href: appPath("/notifications"), label: "Notifications" },
  ],
};

export function homePathForRole(role: string): string {
  const key = (role || "customer") as AppRole;
  return appPath(HOME_BY_ROLE[key] ?? HOME_BY_ROLE.customer);
}

export function topLinksForRole(role: string): NavLink[] {
  const key = (role || "customer") as AppRole;
  return TOP_LINKS_BY_ROLE[key] ?? TOP_LINKS_BY_ROLE.customer;
}

export function sideLinksForRole(role: string): NavLink[] {
  const key = role as AppRole;
  return SIDE_LINKS_BY_ROLE[key] ?? [];
}

export function exitUrlForRole(role: string): string {
  const key = (role || "customer") as AppRole;
  return fullAppPath(HOME_BY_ROLE[key] ?? HOME_BY_ROLE.customer);
}
