import { AuthGuard } from "@/src/components/AuthGuard";
import { Assistify } from "@/components/assistify";

export default function ChatPage() {
  return (
    <AuthGuard>
      <Assistify />
    </AuthGuard>
  );
}
