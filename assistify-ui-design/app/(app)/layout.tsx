import { AuthGuard } from "@/src/components/AuthGuard";
import { RoleGuard } from "@/src/components/RoleGuard";
import { AppShell } from "@/src/components/AppShell";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <RoleGuard>
        <AppShell>{children}</AppShell>
      </RoleGuard>
    </AuthGuard>
  );
}
