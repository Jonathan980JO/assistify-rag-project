"use client";

import { useCallback, useState } from "react";
import { Edit2, Loader2, Plus, Trash2 } from "lucide-react";
import { useUsers } from "@/src/hooks/useUsers";
import { Badge } from "@/src/components/ui/Badge";
import { DataTable, DataTableCell, DataTableRow } from "@/src/components/ui/DataTable";
import { Modal } from "@/src/components/ui/Modal";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { SearchInput } from "@/src/components/ui/SearchInput";

export function UsersPageContent({
  title = "User Management",
  staffMode = "admin",
}: {
  title?: string;
  staffMode?: "admin" | "master_admin";
}) {
  const { users, loading, createUser, deactivate, activate, remove, changeRole, updateProfile } = useUsers();
  const [searchTerm, setSearchTerm] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    role: "customer",
    password: "",
    full_name: "",
  });

  const filteredUsers = users.filter(
    (u) =>
      u.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
      u.email.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const openCreate = useCallback(() => {
    setEditingId(null);
    setFormData({ username: "", email: "", role: "customer", password: "", full_name: "" });
    setShowModal(true);
  }, []);

  const openEdit = useCallback((user: (typeof users)[0]) => {
    setEditingId(user.id);
    setFormData({
      username: user.username,
      email: user.email,
      role: user.role,
      password: "",
      full_name: "",
    });
    setShowModal(true);
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      if (editingId) {
        await changeRole(editingId, formData.role);
        if (formData.email || formData.full_name) {
          await updateProfile(editingId, {
            email: formData.email || undefined,
            full_name: formData.full_name || undefined,
          });
        }
      } else {
        await createUser({
          username: formData.username,
          email: formData.email,
          password: formData.password,
          role: formData.role,
        });
      }
      setShowModal(false);
      setFormData({ username: "", email: "", role: "customer", password: "", full_name: "" });
    } catch {
      // apiClient handles auth redirect
    } finally {
      setSaving(false);
    }
  }, [changeRole, createUser, editingId, formData, updateProfile]);

  const handleInlineRoleChange = async (userId: number, role: string) => {
    await changeRole(userId, role).catch(() => {});
  };

  return (
    <div>
      <PageHeader title={title} subtitle="Manage users, roles, and permissions" />

      <div className="mb-8 flex flex-col gap-4 md:flex-row">
        <SearchInput value={searchTerm} onChange={setSearchTerm} placeholder="Search users..." />
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center justify-center gap-2 rounded-lg bg-[#10a37f] px-6 py-3 font-medium text-white transition-colors hover:bg-[#0d8a68]"
        >
          <Plus className="h-5 w-5" />
          Add User
        </button>
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading users...</p>
      ) : (
        <DataTable
          headers={["Username", "Email", "Role", "Status", "Actions"]}
          isEmpty={filteredUsers.length === 0}
          emptyMessage="No users found"
        >
          {filteredUsers.map((u) => (
            <DataTableRow key={u.id}>
              <DataTableCell className="font-medium">{u.username}</DataTableCell>
              <DataTableCell className="text-[#9ca3af]">{u.email}</DataTableCell>
              <DataTableCell>
                <div className="flex items-center gap-2">
                  <Badge variant="role">{u.role}</Badge>
                  <select
                    className="rounded border border-[#333] bg-[#232323] px-2 py-1 text-xs text-[#fafaff]"
                    value={u.role}
                    onChange={(e) => handleInlineRoleChange(u.id, e.target.value)}
                  >
                    <option value="customer">Customer</option>
                    <option value="employee">Employee</option>
                    {staffMode === "master_admin" && <option value="admin">Admin</option>}
                  </select>
                </div>
              </DataTableCell>
              <DataTableCell>
                <button
                  type="button"
                  onClick={() => (u.active ? deactivate(u.id) : activate(u.id)).catch(() => {})}
                  className="cursor-pointer"
                >
                  <Badge variant="status">{u.active ? "active" : "inactive"}</Badge>
                </button>
              </DataTableCell>
              <DataTableCell>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => openEdit(u)}
                    className="rounded-lg p-2 text-[#9ca3af] transition-colors hover:bg-[#333333] hover:text-[#10a37f]"
                    aria-label="Edit user"
                  >
                    <Edit2 className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(u.id).catch(() => {})}
                    className="rounded-lg p-2 text-[#9ca3af] transition-colors hover:bg-[#333333] hover:text-red-400"
                    aria-label="Delete user"
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
        title={editingId ? "Edit User" : "Create New User"}
        footer={
          <>
            <button
              type="button"
              onClick={() => setShowModal(false)}
              className="flex-1 rounded-lg bg-[#333333] px-4 py-2 font-medium text-[#fafaff] transition-colors hover:bg-[#444444]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[#10a37f] px-4 py-2 font-medium text-white transition-colors hover:bg-[#0d8a68] disabled:opacity-50"
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                "Save User"
              )}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-2 block text-sm font-medium text-[#9ca3af]">Username</label>
            <input
              type="text"
              value={formData.username}
              disabled={Boolean(editingId)}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none disabled:opacity-60"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-[#9ca3af]">Email</label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
            />
          </div>
          {editingId && (
            <div>
              <label className="mb-2 block text-sm font-medium text-[#9ca3af]">Full name</label>
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
              />
            </div>
          )}
          <div>
            <label className="mb-2 block text-sm font-medium text-[#9ca3af]">Role</label>
            <select
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
            >
              <option value="customer">Customer</option>
              <option value="employee">Employee</option>
              {staffMode === "master_admin" && <option value="admin">Admin</option>}
            </select>
          </div>
          {!editingId && (
            <div>
              <label className="mb-2 block text-sm font-medium text-[#9ca3af]">Password</label>
              <input
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
              />
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
