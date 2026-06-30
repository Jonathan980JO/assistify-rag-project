"use client";

import { useState } from "react";
import { Edit2, KeyRound, Loader2, StickyNote } from "lucide-react";
import { useCustomers } from "@/src/hooks/useCustomers";
import { useAnalytics } from "@/src/hooks/useAnalytics";
import { Badge } from "@/src/components/ui/Badge";
import { Card } from "@/src/components/ui/Card";
import { DataTable, DataTableCell, DataTableRow } from "@/src/components/ui/DataTable";
import { Modal } from "@/src/components/ui/Modal";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";
import type { CustomerNote } from "@/src/hooks/useCustomers";

export function CustomersPageContent() {
  const { customers, loading, updateProfile, activate, deactivate, triggerPasswordReset, getNotes, addNote, deleteNote } =
    useCustomers();
  const { summary, loading: analyticsLoading } = useAnalytics({ mode: "employee" });

  const [editOpen, setEditOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ email: "", full_name: "" });
  const [notes, setNotes] = useState<CustomerNote[]>([]);
  const [newNote, setNewNote] = useState("");
  const [saving, setSaving] = useState(false);

  const selected = customers.find((c) => c.id === selectedId);

  const openEdit = (id: number) => {
    const c = customers.find((x) => x.id === id);
    if (!c) return;
    setSelectedId(id);
    setEditForm({ email: c.email, full_name: c.full_name ?? "" });
    setEditOpen(true);
  };

  const openNotes = async (id: number) => {
    setSelectedId(id);
    setNotesOpen(true);
    const data = await getNotes(id);
    setNotes(data.notes ?? []);
    setNewNote("");
  };

  const saveEdit = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await updateProfile(selectedId, editForm);
      setEditOpen(false);
    } finally {
      setSaving(false);
    }
  };

  const handleAddNote = async () => {
    if (!selectedId || !newNote.trim()) return;
    await addNote(selectedId, newNote.trim());
    const data = await getNotes(selectedId);
    setNotes(data.notes ?? []);
    setNewNote("");
  };

  const stats = summary as {
    total_customers?: number;
    active_customers?: number;
    inactive_customers?: number;
    recent_registrations_30d?: number;
  } | null;

  return (
    <div>
      <PageHeader title="Customers" subtitle="Manage customer accounts and support notes" />

      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Total" value={analyticsLoading ? "—" : String(stats?.total_customers ?? 0)} colorClass="text-[#10a37f]" />
        <StatCard label="Active" value={analyticsLoading ? "—" : String(stats?.active_customers ?? 0)} colorClass="text-[#2563eb]" />
        <StatCard label="Inactive" value={analyticsLoading ? "—" : String(stats?.inactive_customers ?? 0)} colorClass="text-[#f59e0b]" />
        <StatCard label="New (30d)" value={analyticsLoading ? "—" : String(stats?.recent_registrations_30d ?? 0)} colorClass="text-[#6c63ff]" />
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading customers...</p>
      ) : (
        <DataTable headers={["Username", "Email", "Status", "Actions"]} isEmpty={customers.length === 0} emptyMessage="No customers">
          {customers.map((c) => (
            <DataTableRow key={c.id}>
              <DataTableCell className="font-medium">{c.username}</DataTableCell>
              <DataTableCell className="text-[#9ca3af]">{c.email}</DataTableCell>
              <DataTableCell>
                <button type="button" onClick={() => (c.active ? deactivate(c.id) : activate(c.id)).catch(() => {})}>
                  <Badge variant="status">{c.active ? "active" : "inactive"}</Badge>
                </button>
              </DataTableCell>
              <DataTableCell>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => openEdit(c.id)}
                    className="flex items-center gap-1 rounded-lg bg-[#10a37f] px-3 py-1.5 text-xs text-white"
                  >
                    <Edit2 className="h-3 w-3" /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => openNotes(c.id).catch(() => {})}
                    className="flex items-center gap-1 rounded-lg bg-[#333333] px-3 py-1.5 text-xs text-[#fafaff]"
                  >
                    <StickyNote className="h-3 w-3" /> Notes
                  </button>
                  <button
                    type="button"
                    onClick={() => triggerPasswordReset(c.id).catch(() => {})}
                    className="flex items-center gap-1 rounded-lg bg-[#2563eb] px-3 py-1.5 text-xs text-white"
                  >
                    <KeyRound className="h-3 w-3" /> Reset pwd
                  </button>
                </div>
              </DataTableCell>
            </DataTableRow>
          ))}
        </DataTable>
      )}

      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title={`Edit profile: ${selected?.username ?? ""}`}
        footer={
          <>
            <button type="button" onClick={() => setEditOpen(false)} className="flex-1 rounded-lg bg-[#333333] px-4 py-2 text-[#fafaff]">
              Cancel
            </button>
            <button type="button" onClick={saveEdit} disabled={saving} className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[#10a37f] px-4 py-2 text-white disabled:opacity-50">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <input
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]"
            placeholder="Email"
            value={editForm.email}
            onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
          />
          <input
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]"
            placeholder="Full name"
            value={editForm.full_name}
            onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
          />
        </div>
      </Modal>

      <Modal open={notesOpen} onClose={() => setNotesOpen(false)} title={`Notes: ${selected?.username ?? ""}`}>
        <div className="mb-4 max-h-48 space-y-2 overflow-y-auto">
          {notes.map((n) => (
            <Card key={n.id} className="flex items-start justify-between p-3">
              <div>
                <p className="text-sm text-[#fafaff]">{n.text}</p>
                <p className="text-xs text-[#9ca3af]">{n.created_at}</p>
              </div>
              <button
                type="button"
                onClick={() => selectedId && deleteNote(selectedId, n.id).then(() => openNotes(selectedId)).catch(() => {})}
                className="text-xs text-red-400"
              >
                Delete
              </button>
            </Card>
          ))}
          {notes.length === 0 && <p className="text-sm text-[#9ca3af]">No notes yet</p>}
        </div>
        <textarea
          className="mb-3 w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-sm text-[#fafaff]"
          placeholder="Add a note..."
          rows={3}
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
        />
        <button type="button" onClick={handleAddNote} className="rounded-lg bg-[#10a37f] px-4 py-2 text-sm text-white">
          Add note
        </button>
      </Modal>
    </div>
  );
}
