"use client";

import { Check, X } from "lucide-react";
import { useAccessRequests } from "@/src/hooks/useAccessRequests";
import { Badge } from "@/src/components/ui/Badge";
import { Card } from "@/src/components/ui/Card";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

export function AccessRequestsPageContent() {
  const { requests, loading, approve, reject } = useAccessRequests();

  const pending = requests.filter((r) => r.status === "pending").length;
  const approved = requests.filter((r) => r.status === "approved").length;
  const rejected = requests.filter((r) => r.status === "rejected").length;

  return (
    <div>
      <PageHeader title="Access Requests" subtitle="Review and manage customer access requests" />

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <StatCard icon={<Check className="h-6 w-6" />} label="Pending" value={String(pending)} colorClass="text-[#f6c33c]" />
        <StatCard icon={<Check className="h-6 w-6" />} label="Approved" value={String(approved)} colorClass="text-[#10a37f]" />
        <StatCard icon={<X className="h-6 w-6" />} label="Rejected" value={String(rejected)} colorClass="text-red-400" />
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading requests...</p>
      ) : (
        <div className="space-y-3">
          {requests.map((r) => (
            <Card key={r.id} className="flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="font-medium text-[#fafaff]">{r.business_name}</p>
                <p className="text-sm text-[#9ca3af]">{r.username}</p>
                <div className="mt-2">
                  <Badge variant="status">{r.status}</Badge>
                </div>
              </div>
              {r.status === "pending" && (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="flex items-center gap-1 rounded-lg bg-[#10a37f] px-4 py-2 text-sm text-white hover:bg-[#0d8a68]"
                    onClick={() => approve(r.id).catch(() => {})}
                  >
                    <Check className="h-4 w-4" />
                    Approve
                  </button>
                  <button
                    type="button"
                    className="flex items-center gap-1 rounded-lg border border-[#444] px-4 py-2 text-sm text-[#9ca3af] hover:text-[#fafaff]"
                    onClick={() => reject(r.id).catch(() => {})}
                  >
                    <X className="h-4 w-4" />
                    Reject
                  </button>
                </div>
              )}
            </Card>
          ))}
          {requests.length === 0 && (
            <p className="py-8 text-center text-[#9ca3af]">No access requests</p>
          )}
        </div>
      )}
    </div>
  );
}
