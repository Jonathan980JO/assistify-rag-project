import { ReactNode } from "react";
import { Card } from "./Card";

export function StatCard({
  icon,
  label,
  value,
  change,
  colorClass = "text-[#10a37f]",
}: {
  icon?: ReactNode;
  label: string;
  value: string;
  change?: string;
  colorClass?: string;
}) {
  return (
    <Card className="p-4 sm:p-6">
      <div className="mb-3 flex items-center justify-between sm:mb-4">
        {icon ? <div className={colorClass}>{icon}</div> : <div />}
        {change && <span className="text-xs font-medium text-[#9ca3af]">{change}</span>}
      </div>
      <p className="text-xs text-[#9ca3af] sm:text-sm">{label}</p>
      <p className="mt-1 text-xl font-bold text-[#fafaff] sm:text-2xl">{value}</p>
    </Card>
  );
}
