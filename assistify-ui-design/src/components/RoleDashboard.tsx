import type { ReactNode } from "react";
import Link from "next/link";
import {
  BarChart3,
  BookOpen,
  Clipboard,
  Lock,
  Shield,
  Ticket,
  Users,
} from "lucide-react";
import { appPath } from "@/src/lib/routes";
import { Card } from "@/src/components/ui/Card";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

const ICONS: Record<string, ReactNode> = {
  Users: <Users className="h-6 w-6" />,
  Knowledge: <BookOpen className="h-6 w-6" />,
  Analytics: <BarChart3 className="h-6 w-6" />,
  "Audit Logs": <Clipboard className="h-6 w-6" />,
  "Access Requests": <Lock className="h-6 w-6" />,
  Tickets: <Ticket className="h-6 w-6" />,
  "Manage Admins": <Shield className="h-6 w-6" />,
};

export function RoleDashboard({
  title,
  subtitle,
  links,
  stats,
}: {
  title: string;
  subtitle: string;
  links: readonly (readonly [string, string])[];
  stats?: { label: string; value: string; change?: string; colorClass?: string; iconKey: string }[];
}) {
  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} />

      {stats && stats.length > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:mb-8 sm:gap-6 lg:grid-cols-4">
          {stats.map((s) => (
            <StatCard
              key={s.label}
              icon={ICONS[s.iconKey] ?? <BarChart3 className="h-6 w-6" />}
              label={s.label}
              value={s.value}
              change={s.change}
              colorClass={s.colorClass}
            />
          ))}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {links.map(([label, path]) => (
          <Link key={path} href={appPath(path)}>
            <Card className="flex items-center gap-4 p-5 transition-colors hover:border-[#10a37f]">
              <div className="text-[#10a37f]">{ICONS[label] ?? <BarChart3 className="h-6 w-6" />}</div>
              <span className="font-medium text-[#fafaff]">{label}</span>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
