import { LogOut } from "lucide-react";

type LogoutLinkProps = {
  className?: string;
};

export function LogoutLink({ className = "" }: LogoutLinkProps) {
  const base =
    "flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium text-[#9ca3af] transition-colors hover:bg-[#2b2b2b] hover:text-[#fafaff]";

  return (
    <a href="/logout" className={`${base} ${className}`.trim()}>
      <LogOut className="h-5 w-5" />
      <span>Logout</span>
    </a>
  );
}
