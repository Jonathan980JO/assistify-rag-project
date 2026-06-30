export type AppLanguage = "en" | "ar";

export type AppRole =
  | "superadmin"
  | "master_admin"
  | "admin"
  | "employee"
  | "customer";

export interface UserProfile {
  username: string;
  email: string;
  full_name?: string;
  role: AppRole;
  created_at?: string;
  active?: boolean;
  tenant_id?: number | null;
  tenant_name?: string | null;
  tenant_slug?: string | null;
}

export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}

export interface ConversationMessage {
  id?: string;
  role: "user" | "assistant" | "system";
  text: string;
  content?: string;
  tenant_id?: number;
  created_at?: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  messages: ConversationMessage[];
  active_tenant_id?: number;
  created_at?: string;
  updated_at?: string;
}

export interface ChatTenant {
  id: number;
  name: string;
  slug?: string;
}

export interface NotificationItem {
  id: number;
  title: string;
  message: string;
  read: boolean;
  created_at: string;
  link?: string;
}

export interface SupportTicket {
  id: number;
  subject: string;
  status: string;
  priority?: string;
  created_at: string;
  updated_at?: string;
  customer_username?: string;
  assigned_to?: string;
}

export interface AuditLogEntry {
  id: number;
  username?: string;
  action: string;
  old_value?: string;
  new_value?: string;
  ip_address?: string;
  performed_by?: string;
  created_at?: string;
  timestamp?: string;
}
