"use client";

import Link from "next/link";
import { BarChart3, BookOpen, Ticket, Users } from "lucide-react";
import { useAnalytics } from "@/src/hooks/useAnalytics";
import { useKnowledge } from "@/src/hooks/useKnowledge";
import { KnowledgePageContent } from "@/src/features/knowledge/KnowledgePageContent";
import { appPath } from "@/src/lib/routes";
import { Card } from "@/src/components/ui/Card";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

export default function EmployeeDashboardPage() {
  const { summary, loading } = useAnalytics({ mode: "employee" });
  const { files } = useKnowledge();

  const stats = summary as {
    total_customers?: number;
    active_customers?: number;
    total_support_notes?: number;
  } | null;

  return (
    <div>
      <PageHeader title="Employee Dashboard" subtitle="Support customers and manage tickets" />

      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard icon={<Users className="h-6 w-6" />} label="Customers" value={loading ? "—" : String(stats?.total_customers ?? 0)} colorClass="text-[#10a37f]" />
        <StatCard icon={<Users className="h-6 w-6" />} label="Active" value={loading ? "—" : String(stats?.active_customers ?? 0)} colorClass="text-[#2563eb]" />
        <StatCard icon={<BarChart3 className="h-6 w-6" />} label="Support Notes" value={loading ? "—" : String(stats?.total_support_notes ?? 0)} colorClass="text-[#f6c33c]" />
        <StatCard icon={<BookOpen className="h-6 w-6" />} label="KB Documents" value={String(files.length)} colorClass="text-[#6c63ff]" />
      </div>

      <div className="mb-8 grid gap-4 md:grid-cols-2">
        <Link href={appPath("/employee/customers")}>
          <Card className="flex items-center gap-4 p-5 transition-colors hover:border-[#10a37f]">
            <Users className="h-6 w-6 text-[#10a37f]" />
            <span className="font-medium text-[#fafaff]">Manage Customers</span>
          </Card>
        </Link>
        <Link href={appPath("/employee/tickets")}>
          <Card className="flex items-center gap-4 p-5 transition-colors hover:border-[#10a37f]">
            <Ticket className="h-6 w-6 text-[#10a37f]" />
            <span className="font-medium text-[#fafaff]">Support Tickets</span>
          </Card>
        </Link>
      </div>

      <KnowledgePageContent title="Knowledge Base (Read-only)" readOnly />
    </div>
  );
}
