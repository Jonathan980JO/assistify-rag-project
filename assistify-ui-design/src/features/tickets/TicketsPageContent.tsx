"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  filterTickets,
  type TicketDetail,
  type TicketFilter,
  useTickets,
} from "@/src/hooks/useTickets";
import { useProfile } from "@/src/hooks/useProfile";
import type { SupportTicket } from "@/src/lib/types";
import { Badge } from "@/src/components/ui/Badge";
import { Card } from "@/src/components/ui/Card";
import { Modal } from "@/src/components/ui/Modal";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

const FILTERS: { key: TicketFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "escalated", label: "Escalated" },
  { key: "high", label: "High Priority" },
  { key: "unassigned", label: "Unassigned" },
  { key: "open", label: "Open" },
  { key: "resolved", label: "Resolved" },
];

export function TicketsPageContent({
  title = "Support Tickets",
  staffRole,
}: {
  title?: string;
  staffRole?: "admin" | "master_admin" | "employee";
}) {
  const isStaff = Boolean(staffRole);
  const { profile } = useProfile();
  const {
    tickets,
    summary,
    loading,
    refresh,
    loadSummary,
    getTicket,
    createTicket,
    sendMessage,
    assign,
    escalate,
    resolve,
  } = useTickets();

  const [filter, setFilter] = useState<TicketFilter>("all");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [priority, setPriority] = useState("normal");
  const [detail, setDetail] = useState<TicketDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [reply, setReply] = useState("");
  const [resolveNotes, setResolveNotes] = useState("");
  const [escalateNote, setEscalateNote] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    if (isStaff) loadSummary().catch(() => {});
  }, [isStaff, loadSummary]);

  const openDetail = useCallback(
    async (ticketId: number) => {
      setDetailLoading(true);
      try {
        const data = await getTicket(ticketId);
        setDetail(data);
        setReply("");
        setResolveNotes("");
        setEscalateNote("");
      } finally {
        setDetailLoading(false);
      }
    },
    [getTicket],
  );

  const closeDetail = () => setDetail(null);

  const refreshDetail = async (ticketId: number) => {
    const data = await getTicket(ticketId);
    setDetail(data);
    await refresh();
    if (isStaff) await loadSummary();
  };

  const filtered = filterTickets(tickets, filter);

  const ticketLabel = (t: SupportTicket) => {
    const ext = t as SupportTicket & { customer?: string; ticket_number?: string };
    return ext.ticket_number ? `#${ext.ticket_number}` : `#${t.id}`;
  };

  return (
    <div>
      <PageHeader title={title} subtitle="Track and resolve support tickets" />

      {isStaff && summary && (
        <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Total" value={String(summary.total_tickets)} colorClass="text-[#10a37f]" />
          <StatCard label="Open" value={String(summary.open_tickets)} colorClass="text-[#2563eb]" />
          <StatCard label="Escalated" value={String(summary.escalated_tickets)} colorClass="text-[#f59e0b]" />
          <StatCard label="Resolved Today" value={String(summary.resolved_today)} colorClass="text-[#6c63ff]" />
        </div>
      )}

      {!isStaff && (
        <Card className="mb-8 p-6">
          <h2 className="mb-4 text-lg font-semibold text-[#fafaff]">New ticket</h2>
          <input
            className="mb-3 w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
            placeholder="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <textarea
            className="mb-3 w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
            placeholder="Describe your issue..."
            rows={4}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <select
            className="mb-3 w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </select>
          <button
            type="button"
            className="rounded-lg bg-[#10a37f] px-6 py-2 text-sm font-medium text-white hover:bg-[#0d8a68]"
            onClick={() => createTicket(subject, message, priority).catch(() => {})}
          >
            Submit ticket
          </button>
        </Card>
      )}

      {isStaff && (
        <div className="mb-6 flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`rounded-lg px-4 py-2 text-sm transition-colors ${
                filter === f.key
                  ? "bg-[#10a37f] text-white"
                  : "bg-[#2b2b2b] text-[#9ca3af] hover:text-[#fafaff]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <p className="text-[#9ca3af]">Loading tickets...</p>
      ) : (
        <div className="space-y-3">
          {filtered.map((t) => {
            const ext = t as SupportTicket & { customer?: string };
            return (
              <Card
                key={t.id}
                className="cursor-pointer p-4 transition-colors hover:border-[#10a37f]"
                onClick={() => openDetail(t.id)}
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="font-medium text-[#fafaff]">
                      {ticketLabel(t)} — {t.subject}
                    </p>
                    <p className="text-sm text-[#9ca3af]">
                      {ext.customer ?? t.customer_username ?? "—"}
                      {t.priority ? ` · ${t.priority}` : ""}
                    </p>
                    <div className="mt-2 flex gap-2">
                      <Badge variant="status">{t.status}</Badge>
                      {(t as SupportTicket & { escalated?: boolean }).escalated && (
                        <Badge variant="role">escalated</Badge>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
          {filtered.length === 0 && (
            <p className="py-8 text-center text-[#9ca3af]">No tickets yet</p>
          )}
        </div>
      )}

      <Modal
        open={detail !== null || detailLoading}
        onClose={closeDetail}
        title={detail ? `${detail.ticket_number ? `#${detail.ticket_number}` : `#${detail.id}`} — ${detail.subject}` : "Loading ticket..."}
        footer={
          detail ? (
            <button
              type="button"
              onClick={closeDetail}
              className="w-full rounded-lg bg-[#333333] px-4 py-2 text-[#fafaff]"
            >
              Close
            </button>
          ) : null
        }
      >
        {detailLoading && !detail ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-[#10a37f]" />
          </div>
        ) : detail ? (
          <div className="space-y-4">
            <p className="text-sm text-[#9ca3af]">{detail.description}</p>
            <div className="max-h-64 space-y-3 overflow-y-auto rounded-lg bg-[#232323] p-4">
              {(detail.messages ?? []).map((m) => (
                <div key={m.id} className="text-sm">
                  <p className="font-medium text-[#10a37f]">
                    {m.sender} <span className="text-xs text-[#9ca3af]">({m.role})</span>
                  </p>
                  <p className="text-[#fafaff]">{m.message}</p>
                  <p className="text-xs text-[#9ca3af]">{m.created_at}</p>
                </div>
              ))}
              {(detail.messages ?? []).length === 0 && (
                <p className="text-[#9ca3af]">No messages yet</p>
              )}
            </div>

            {detail.status !== "resolved" && (
              <>
                <textarea
                  className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-sm text-[#fafaff]"
                  placeholder="Write a reply..."
                  rows={3}
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                />
                <button
                  type="button"
                  disabled={!reply.trim() || actionLoading}
                  className="rounded-lg bg-[#10a37f] px-4 py-2 text-sm text-white disabled:opacity-50"
                  onClick={async () => {
                    setActionLoading(true);
                    try {
                      await sendMessage(detail.id, reply.trim());
                      await refreshDetail(detail.id);
                      setReply("");
                    } finally {
                      setActionLoading(false);
                    }
                  }}
                >
                  Send reply
                </button>
              </>
            )}

            {isStaff && detail.status !== "resolved" && (
              <div className="space-y-3 border-t border-[#333] pt-4">
                <button
                  type="button"
                  disabled={actionLoading}
                  className="mr-2 rounded-lg bg-[#2563eb] px-4 py-2 text-sm text-white disabled:opacity-50"
                  onClick={async () => {
                    setActionLoading(true);
                    try {
                      await assign(detail.id, profile?.username);
                      await refreshDetail(detail.id);
                    } finally {
                      setActionLoading(false);
                    }
                  }}
                >
                  Assign to me
                </button>

                {staffRole === "employee" && (
                  <>
                    <textarea
                      className="mt-3 w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-sm text-[#fafaff]"
                      placeholder="Escalation note (required)..."
                      rows={2}
                      value={escalateNote}
                      onChange={(e) => setEscalateNote(e.target.value)}
                    />
                    <button
                      type="button"
                      disabled={!escalateNote.trim() || actionLoading}
                      className="rounded-lg bg-[#f59e0b] px-4 py-2 text-sm text-white disabled:opacity-50"
                      onClick={async () => {
                        setActionLoading(true);
                        try {
                          await escalate(detail.id, escalateNote.trim());
                          await refreshDetail(detail.id);
                          setEscalateNote("");
                        } finally {
                          setActionLoading(false);
                        }
                      }}
                    >
                      Escalate to admin
                    </button>
                  </>
                )}

                <textarea
                  className="mt-3 w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-sm text-[#fafaff]"
                  placeholder="Resolution notes (optional)..."
                  rows={2}
                  value={resolveNotes}
                  onChange={(e) => setResolveNotes(e.target.value)}
                />
                <button
                  type="button"
                  disabled={actionLoading}
                  className="rounded-lg bg-[#10a37f] px-4 py-2 text-sm text-white disabled:opacity-50"
                  onClick={async () => {
                    setActionLoading(true);
                    try {
                      await resolve(detail.id, resolveNotes.trim());
                      await refreshDetail(detail.id);
                    } finally {
                      setActionLoading(false);
                    }
                  }}
                >
                  Resolve ticket
                </button>
              </div>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
