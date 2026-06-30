"use client";

import { AlertCircle, Bell, CheckCircle, Info } from "lucide-react";
import { useNotifications } from "@/src/hooks/useNotifications";
import { Card } from "@/src/components/ui/Card";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

function typeIcon() {
  return <Info className="h-5 w-5" />;
}

export default function NotificationsPage() {
  const { items, loading, markRead, markAllRead } = useNotifications();
  const unread = items.filter((n) => !n.read).length;

  return (
    <div>
      <PageHeader title="Notifications" subtitle="Stay updated on system activity" />

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <StatCard icon={<Bell className="h-6 w-6" />} label="Total" value={String(items.length)} colorClass="text-[#10a37f]" />
        <StatCard icon={<AlertCircle className="h-6 w-6" />} label="Unread" value={String(unread)} colorClass="text-[#f6c33c]" />
        <StatCard icon={<CheckCircle className="h-6 w-6" />} label="Read" value={String(items.length - unread)} colorClass="text-[#2563eb]" />
      </div>

      <div className="mb-6 flex justify-end">
        <button
          type="button"
          className="rounded-lg bg-[#10a37f] px-4 py-2 text-sm font-medium text-white hover:bg-[#0d8a68]"
          onClick={() => markAllRead().catch(() => {})}
        >
          Mark all read
        </button>
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading notifications...</p>
      ) : (
        <div className="space-y-3">
          {items.map((n) => (
              <Card
                key={n.id}
                className={`border p-4 ${n.read ? "opacity-60" : ""}`}
              >
                <div className="flex items-start gap-4">
                  <div className="text-[#2563eb]">
                    {typeIcon()}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-[#fafaff]">{n.title}</p>
                    <p className="mt-1 text-sm text-[#9ca3af]">{n.message}</p>
                    {!n.read && (
                      <button
                        type="button"
                        className="mt-3 text-sm text-[#10a37f] hover:underline"
                        onClick={() => markRead(n.id).catch(() => {})}
                      >
                        Mark as read
                      </button>
                    )}
                  </div>
                </div>
              </Card>
          ))}
          {items.length === 0 && (
            <p className="py-8 text-center text-[#9ca3af]">No notifications</p>
          )}
        </div>
      )}
    </div>
  );
}
