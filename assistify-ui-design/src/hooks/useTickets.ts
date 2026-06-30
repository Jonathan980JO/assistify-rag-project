"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/src/lib/apiClient";
import type { SupportTicket } from "@/src/lib/types";

export interface TicketMessage {
  id: number;
  sender: string;
  role: string;
  message: string;
  is_internal?: boolean;
  created_at: string;
}

export interface TicketDetail extends SupportTicket {
  ticket_number?: string;
  description?: string;
  customer?: string;
  assigned_to_role?: string;
  escalated?: boolean;
  resolution_notes?: string;
  messages?: TicketMessage[];
}

export interface TicketSummary {
  total_tickets: number;
  open_tickets: number;
  escalated_tickets: number;
  resolved_today: number;
  by_priority?: Record<string, number>;
}

export type TicketFilter = "all" | "open" | "escalated" | "high" | "unassigned" | "resolved";

export function useTickets() {
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [summary, setSummary] = useState<TicketSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<{ tickets: SupportTicket[] }>("/api/support/tickets");
      setTickets(data.tickets ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSummary = useCallback(async () => {
    try {
      const data = await apiClient.get<TicketSummary>("/api/admin/support/summary");
      setSummary(data);
    } catch {
      setSummary(null);
    }
  }, []);

  const getTicket = useCallback(async (ticketId: number) => {
    return apiClient.get<TicketDetail>(`/api/support/ticket/${ticketId}`);
  }, []);

  const createTicket = useCallback(
    async (subject: string, message: string, priority = "normal") => {
      await apiClient.post("/api/support/ticket/create", { subject, message, priority });
      await refresh();
    },
    [refresh],
  );

  const sendMessage = useCallback(async (ticketId: number, message: string) => {
    await apiClient.post(`/api/support/ticket/${ticketId}/message`, { message });
  }, []);

  const assign = useCallback(
    async (ticketId: number, assignTo?: string) => {
      await apiClient.post(`/api/support/ticket/${ticketId}/assign`, {
        assign_to: assignTo,
      });
      await refresh();
    },
    [refresh],
  );

  const escalate = useCallback(
    async (ticketId: number, note: string) => {
      await apiClient.post(`/api/support/ticket/${ticketId}/escalate`, { note });
      await refresh();
    },
    [refresh],
  );

  const resolve = useCallback(
    async (ticketId: number, resolutionNotes = "") => {
      await apiClient.post(`/api/support/ticket/${ticketId}/resolve`, {
        resolution_notes: resolutionNotes,
      });
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return {
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
  };
}

export function filterTickets(tickets: SupportTicket[], filter: TicketFilter): SupportTicket[] {
  return tickets.filter((t) => {
    const ticket = t as SupportTicket & {
      escalated?: boolean;
      customer?: string;
      assigned_to?: string;
    };
    switch (filter) {
      case "open":
        return t.status === "open";
      case "resolved":
        return t.status === "resolved";
      case "escalated":
        return Boolean(ticket.escalated);
      case "high":
        return t.priority === "high" || t.priority === "urgent";
      case "unassigned":
        return !ticket.assigned_to && t.status !== "resolved";
      default:
        return true;
    }
  });
}
