import { cn } from "@/lib/utils";

const ROLE_STYLES: Record<string, string> = {
  admin: "bg-[#2563eb]/20 text-[#2563eb]",
  master_admin: "bg-[#2563eb]/20 text-[#2563eb]",
  employee: "bg-[#f6c33c]/20 text-[#f6c33c]",
  customer: "bg-[#10a37f]/20 text-[#10a37f]",
  superadmin: "bg-[#6c63ff]/20 text-[#6c63ff]",
};

const STATUS_STYLES: Record<string, string> = {
  active: "bg-[#10a37f]/20 text-[#10a37f]",
  inactive: "bg-red-500/20 text-red-400",
  pending: "bg-[#f6c33c]/20 text-[#f6c33c]",
  approved: "bg-[#10a37f]/20 text-[#10a37f]",
  rejected: "bg-red-500/20 text-red-400",
  resolved: "bg-[#10a37f]/20 text-[#10a37f]",
  open: "bg-[#2563eb]/20 text-[#2563eb]",
};

export function Badge({
  children,
  variant = "default",
  className,
}: {
  children: React.ReactNode;
  variant?: "default" | "role" | "status";
  className?: string;
}) {
  const key = String(children).toLowerCase();
  const preset =
    variant === "role"
      ? ROLE_STYLES[key]
      : variant === "status"
        ? STATUS_STYLES[key]
        : "bg-[#333333] text-[#fafaff]";

  return (
    <span
      className={cn(
        "inline-flex rounded-full px-3 py-1 text-xs font-medium",
        preset ?? "bg-[#333333] text-[#fafaff]",
        className,
      )}
    >
      {children}
    </span>
  );
}
