"use client";

import { useState } from "react";
import { Edit2, Loader2, Plus, Shield, Trash2 } from "lucide-react";
import { useTenantAdmins } from "@/src/hooks/useTenantAdmins";
import { Badge } from "@/src/components/ui/Badge";
import { Card } from "@/src/components/ui/Card";
import { DataTable, DataTableCell, DataTableRow } from "@/src/components/ui/DataTable";
import { Modal } from "@/src/components/ui/Modal";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

export default function MasterAdminAdminsPage() {
  const { admins, loading, createAdmin, updateAdmin, removeAdmin } = useTenantAdmins();
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [form, setForm] = useState({ username: "", email: "", password: "", full_name: "" });

  const openCreate = () => {
    setEditingId(null);
    setForm({ username: "", email: "", password: "", full_name: "" });
    setFormError("");
    setShowModal(true);
  };

  const openEdit = (admin: (typeof admins)[0]) => {
    setEditingId(admin.id);
    setForm({
      username: admin.username,
      email: admin.email,
      password: "",
      full_name: admin.full_name ?? "",
    });
    setFormError("");
    setShowModal(true);
  };

  const validateForm = (): string | null => {
    if (!editingId) {
      if (!form.password.trim()) {
        return "Please enter Password";
      }
      if (form.password.length < 8) {
        return "Password must be at least 8 characters.";
      }
    } else if (form.password && form.password.length < 8) {
      return "Password must be at least 8 characters.";
    }
    return null;
  };

  const handleSave = async () => {
    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }

    setFormError("");
    setSaving(true);
    try {
      if (editingId) {
        const payload: Record<string, string> = {
          email: form.email,
          full_name: form.full_name,
        };
        if (form.password) payload.password = form.password;
        await updateAdmin(editingId, payload);
      } else {
        await createAdmin(form);
      }
      setShowModal(false);
      setForm({ username: "", email: "", password: "", full_name: "" });
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to save admin");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader title="Tenant Admins" subtitle="Manage administrators for your business" />

      <div className="mb-8 grid gap-4 md:grid-cols-2">
        <StatCard icon={<Shield className="h-6 w-6" />} label="Total Admins" value={String(admins.length)} colorClass="text-[#10a37f]" />
        <StatCard icon={<Shield className="h-6 w-6" />} label="Active" value={String(admins.filter((a) => a.active).length)} colorClass="text-[#2563eb]" />
      </div>

      <div className="mb-8">
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-2 rounded-lg bg-[#10a37f] px-6 py-3 font-medium text-white hover:bg-[#0d8a68]"
        >
          <Plus className="h-5 w-5" />
          Invite admin
        </button>
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading admins...</p>
      ) : (
        <DataTable headers={["Username", "Email", "Status", "Actions"]} isEmpty={admins.length === 0} emptyMessage="No tenant admins">
          {admins.map((a) => (
            <DataTableRow key={a.id}>
              <DataTableCell className="font-medium">{a.username}</DataTableCell>
              <DataTableCell className="text-[#9ca3af]">{a.email}</DataTableCell>
              <DataTableCell>
                <Badge variant="status">{a.active ? "active" : "inactive"}</Badge>
              </DataTableCell>
              <DataTableCell>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => openEdit(a)}
                    className="rounded-lg p-2 text-[#9ca3af] hover:bg-[#333333] hover:text-[#10a37f]"
                    aria-label="Edit admin"
                  >
                    <Edit2 className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeAdmin(a.id).catch(() => {})}
                    className="rounded-lg p-2 text-[#9ca3af] hover:bg-[#333333] hover:text-red-400"
                    aria-label="Remove admin"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </DataTableCell>
            </DataTableRow>
          ))}
        </DataTable>
      )}

      <Modal
        open={showModal}
        onClose={() => setShowModal(false)}
        title={editingId ? "Edit tenant admin" : "Invite tenant admin"}
        footer={
          <>
            <button type="button" onClick={() => setShowModal(false)} className="flex-1 rounded-lg bg-[#333333] px-4 py-2 text-[#fafaff]">
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[#10a37f] px-4 py-2 text-white disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {editingId ? "Save changes" : "Invite"}
            </button>
          </>
        }
      >
        {formError && (
          <p className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formError}
          </p>
        )}
        <div className="space-y-4">
          <input
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] disabled:opacity-60"
            placeholder="Username"
            value={form.username}
            disabled={Boolean(editingId)}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
          <input className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]" type="password" placeholder={editingId ? "New password (optional)" : "Password"} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <input className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]" placeholder="Full name (optional)" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </div>
      </Modal>
    </div>
  );
}
