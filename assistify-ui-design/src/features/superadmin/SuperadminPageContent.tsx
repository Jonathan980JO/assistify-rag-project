"use client";

import { useState } from "react";
import {
  Building2,
  ChevronDown,
  ChevronUp,
  Edit2,
  Loader2,
  Plus,
  Shield,
  Trash2,
  UserPlus,
} from "lucide-react";
import { slugFromName, type Tenant, type TenantUser, useTenants } from "@/src/hooks/useTenants";
import { Badge } from "@/src/components/ui/Badge";
import { Card } from "@/src/components/ui/Card";
import { DataTable, DataTableCell, DataTableRow } from "@/src/components/ui/DataTable";
import { Modal } from "@/src/components/ui/Modal";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { StatCard } from "@/src/components/ui/StatCard";

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function UserList({ title, users }: { title: string; users: TenantUser[] }) {
  if (!users.length) return null;
  return (
    <div className="mb-4">
      <h4 className="mb-2 text-sm font-semibold text-[#fafaff]">{title}</h4>
      <ul className="space-y-1 text-sm text-[#9ca3af]">
        {users.map((u) => (
          <li key={u.id}>
            {u.username}
            {u.email ? ` · ${u.email}` : ""}
            {!u.active && <span className="ml-2 text-yellow-400">(inactive)</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SuperadminPageContent() {
  const {
    tenants,
    loading,
    createTenant,
    activate,
    deactivate,
    createManager,
    updateManager,
    deleteManager,
    updateSettings,
    deleteTenant,
  } = useTenants();

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createSlug, setCreateSlug] = useState("");
  const [createError, setCreateError] = useState("");
  const [createSaving, setCreateSaving] = useState(false);

  const [deleteModal, setDeleteModal] = useState<Tenant | null>(null);
  const [confirmSlug, setConfirmSlug] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleteSaving, setDeleteSaving] = useState(false);

  const [managerModal, setManagerModal] = useState<{
    mode: "create" | "edit";
    tenantId: number;
    user?: TenantUser;
  } | null>(null);
  const [managerForm, setManagerForm] = useState({
    username: "",
    password: "",
    email: "",
    full_name: "",
    active: true,
  });
  const [managerError, setManagerError] = useState("");
  const [managerSaving, setManagerSaving] = useState(false);

  const activeCount = tenants.filter((t) => t.active).length;

  const handleNameChange = (value: string) => {
    setCreateName(value);
    if (!createSlug || createSlug === slugFromName(createName)) {
      setCreateSlug(slugFromName(value));
    }
  };

  const handleCreateTenant = async () => {
    setCreateError("");
    setCreateSaving(true);
    try {
      await createTenant({ name: createName, slug: createSlug || slugFromName(createName) });
      setCreateName("");
      setCreateSlug("");
      setShowCreateForm(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create business");
    } finally {
      setCreateSaving(false);
    }
  };

  const openCreateManager = (tenantId: number) => {
    setManagerForm({ username: "", password: "", email: "", full_name: "", active: true });
    setManagerError("");
    setManagerModal({ mode: "create", tenantId });
  };

  const openEditManager = (tenantId: number, user: TenantUser) => {
    setManagerForm({
      username: user.username,
      password: "",
      email: user.email ?? "",
      full_name: user.full_name ?? "",
      active: user.active,
    });
    setManagerError("");
    setManagerModal({ mode: "edit", tenantId, user });
  };

  const validateManagerForm = (): string | null => {
    if (managerModal?.mode === "create") {
      if (!managerForm.username.trim() || !managerForm.password) {
        return "Username and password are required.";
      }
      if (managerForm.password.length < 8) {
        return "Password must be at least 8 characters.";
      }
    } else if (managerForm.password && managerForm.password.length < 8) {
      return "Password must be at least 8 characters.";
    }

    const email = managerForm.email.trim();
    if (email && !isValidEmail(email)) {
      return "Please enter a valid email address.";
    }

    return null;
  };

  const handleSaveManager = async () => {
    if (!managerModal) return;

    const validationError = validateManagerForm();
    if (validationError) {
      setManagerError(validationError);
      return;
    }

    setManagerError("");
    setManagerSaving(true);
    try {
      if (managerModal.mode === "create") {
        await createManager(managerModal.tenantId, {
          username: managerForm.username.trim(),
          password: managerForm.password,
          email: managerForm.email.trim() || undefined,
          full_name: managerForm.full_name.trim() || undefined,
        });
      } else if (managerModal.user) {
        const payload: {
          email?: string;
          full_name?: string;
          password?: string;
          active?: boolean;
        } = {
          email: managerForm.email.trim() || undefined,
          full_name: managerForm.full_name.trim() || undefined,
          active: managerForm.active,
        };
        if (managerForm.password) payload.password = managerForm.password;
        await updateManager(managerModal.tenantId, managerModal.user.id, payload);
      }
      setManagerModal(null);
    } catch (err) {
      setManagerError(err instanceof Error ? err.message : "Failed to save master admin");
    } finally {
      setManagerSaving(false);
    }
  };

  const handleDeleteManager = async (tenantId: number, user: TenantUser) => {
    if (!window.confirm(`Permanently delete admin "${user.username}"?`)) return;
    try {
      await deleteManager(tenantId, user.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleUpdateSettings = async (tenantId: number, enabled: boolean) => {
    try {
      await updateSettings(tenantId, enabled);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Settings update failed");
    }
  };

  const handleActivate = async (tenantId: number) => {
    try {
      await activate(tenantId);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Activate failed");
    }
  };

  const handleDeactivate = async (tenantId: number) => {
    try {
      await deactivate(tenantId);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Deactivate failed");
    }
  };

  const openDeleteModal = (tenant: Tenant) => {
    setConfirmSlug("");
    setDeleteError("");
    setDeleteModal(tenant);
  };

  const handleDeleteTenant = async () => {
    if (!deleteModal) return;
    setDeleteError("");
    setDeleteSaving(true);
    try {
      await deleteTenant(deleteModal.id, confirmSlug.trim().toLowerCase());
      if (expandedId === deleteModal.id) {
        setExpandedId(null);
      }
      setDeleteModal(null);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleteSaving(false);
    }
  };

  const renderRoleCounts = (t: Tenant) => {
    const counts = t.role_counts ?? {};
    return (
      <div className="mb-4 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
        {(["master_admin", "admin", "employee", "customer"] as const).map((role) => (
          <div key={role} className="rounded-lg bg-[#171717] px-3 py-2">
            <span className="text-[#9ca3af] capitalize">{role.replace("_", " ")}</span>
            <p className="font-semibold text-[#fafaff]">{counts[role] ?? 0}</p>
          </div>
        ))}
      </div>
    );
  };

  const renderMembershipStats = (t: Tenant) => {
    const stats = t.membership_stats ?? {};
    const entries = Object.entries(stats).filter(([, v]) => v > 0);
    if (!entries.length) return null;
    return (
      <div className="mb-4">
        <h4 className="mb-2 text-sm font-semibold text-[#fafaff]">Membership stats</h4>
        <div className="flex flex-wrap gap-2">
          {entries.map(([status, count]) => (
            <Badge key={status} variant="role">
              {status}: {count}
            </Badge>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div>
      <PageHeader title="Super Admin" subtitle="Platform-wide business and tenant management" />

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <StatCard icon={<Building2 className="h-6 w-6" />} label="Businesses" value={String(tenants.length)} colorClass="text-[#10a37f]" />
        <StatCard icon={<Shield className="h-6 w-6" />} label="Active" value={String(activeCount)} colorClass="text-[#2563eb]" />
        <StatCard icon={<Building2 className="h-6 w-6" />} label="Inactive" value={String(tenants.length - activeCount)} colorClass="text-[#f6c33c]" />
      </div>

      <div className="mb-6">
        <button
          type="button"
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="flex items-center gap-2 rounded-lg bg-[#10a37f] px-6 py-3 font-medium text-white hover:bg-[#0d8a68]"
        >
          <Plus className="h-5 w-5" />
          Create business
        </button>
      </div>

      {showCreateForm && (
        <Card className="mb-8 p-6">
          <h2 className="mb-4 text-lg font-semibold text-[#fafaff]">New business</h2>
          {createError && (
            <p className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-400">
              {createError}
            </p>
          )}
          <div className="grid gap-3 md:grid-cols-2">
            <input
              className="rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
              placeholder="Business name"
              value={createName}
              onChange={(e) => handleNameChange(e.target.value)}
            />
            <input
              className="rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
              placeholder="Slug (e.g. acme-corp)"
              value={createSlug}
              onChange={(e) => setCreateSlug(e.target.value.toLowerCase())}
            />
          </div>
          <button
            type="button"
            disabled={createSaving || !createName.trim()}
            className="mt-4 flex items-center gap-2 rounded-lg bg-[#10a37f] px-6 py-2 text-white hover:bg-[#0d8a68] disabled:opacity-50"
            onClick={handleCreateTenant}
          >
            {createSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Create
          </button>
        </Card>
      )}

      {loading ? (
        <p className="text-[#9ca3af]">Loading businesses...</p>
      ) : (
        <div className="space-y-4">
          {tenants.map((t) => {
            const hasMasterAdmin = (t.master_admins?.length ?? 0) > 0;

            return (
              <Card key={t.id} className="overflow-hidden">
                <button
                  type="button"
                  className="flex w-full items-center justify-between p-5 text-left"
                  onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-[#10a37f]/20 text-[#10a37f]">
                      <Building2 className="h-6 w-6" />
                    </div>
                    <div>
                      <p className="font-semibold text-[#fafaff]">{t.name}</p>
                      <p className="text-sm text-[#9ca3af]">
                        {t.slug || `tenant-${t.id}`}
                        {t.plan ? ` · ${t.plan}` : ""}
                        {typeof t.user_count === "number" ? ` · ${t.user_count} users` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="status">{t.active ? "active" : "inactive"}</Badge>
                    {expandedId === t.id ? (
                      <ChevronUp className="h-5 w-5 text-[#9ca3af]" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-[#9ca3af]" />
                    )}
                  </div>
                </button>

                {expandedId === t.id && (
                  <div className="border-t border-[#333333] bg-[#232323] p-5">
                    <p className="mb-4 text-sm text-[#9ca3af]">Created: {t.created_at || "—"}</p>

                    {renderRoleCounts(t)}
                    {renderMembershipStats(t)}

                    <div className="mb-2 flex items-center justify-between">
                      <h4 className="text-sm font-semibold text-[#fafaff]">Master admins</h4>
                      <button
                        type="button"
                        disabled={hasMasterAdmin}
                        title={
                          hasMasterAdmin
                            ? "This tenant already has a master admin. Delete or deactivate the existing one first."
                            : undefined
                        }
                        onClick={() => openCreateManager(t.id)}
                        className="flex items-center gap-1 rounded-lg bg-[#10a37f] px-3 py-1.5 text-xs text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <UserPlus className="h-3 w-3" /> Add master admin
                      </button>
                    </div>
                    <p className="mb-4 text-xs text-[#9ca3af]">
                      One master admin per tenant. Normal admins are created by the master admin.
                    </p>

                    <DataTable
                      headers={["Username", "Full name", "Email", "Status", "Actions"]}
                      isEmpty={!(t.master_admins?.length ?? 0)}
                      emptyMessage="No master admins yet"
                    >
                      {(t.master_admins ?? []).map((m) => (
                        <DataTableRow key={m.id}>
                          <DataTableCell className="font-medium">{m.username}</DataTableCell>
                          <DataTableCell className="text-[#9ca3af]">{m.full_name ?? "—"}</DataTableCell>
                          <DataTableCell className="text-[#9ca3af]">{m.email ?? "—"}</DataTableCell>
                          <DataTableCell>
                            <Badge variant="status">{m.active ? "active" : "inactive"}</Badge>
                          </DataTableCell>
                          <DataTableCell>
                            <div className="flex gap-2">
                              <button
                                type="button"
                                onClick={() => openEditManager(t.id, m)}
                                className="rounded p-1.5 text-[#9ca3af] hover:text-[#10a37f]"
                                aria-label="Edit master admin"
                              >
                                <Edit2 className="h-4 w-4" />
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteManager(t.id, m)}
                                className="rounded p-1.5 text-[#9ca3af] hover:text-red-400"
                                aria-label="Delete master admin"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </div>
                          </DataTableCell>
                        </DataTableRow>
                      ))}
                    </DataTable>

                    <UserList title="Admins" users={t.admins ?? []} />
                    <UserList title="Employees" users={t.employees ?? []} />
                    <UserList title="Approved customers" users={t.membership_customers ?? []} />

                    <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-[#333] pt-4">
                      <label className="flex cursor-pointer items-center gap-2 text-sm text-[#fafaff]">
                        <input
                          type="checkbox"
                          checked={Boolean(t.allow_multiple_admins)}
                          onChange={(e) => handleUpdateSettings(t.id, e.target.checked)}
                          className="rounded border-[#333]"
                        />
                        Allow multiple admins
                      </label>
                      {t.active ? (
                        <button
                          type="button"
                          className="text-sm text-yellow-400 hover:underline"
                          onClick={() => handleDeactivate(t.id)}
                        >
                          Deactivate business
                        </button>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="text-sm text-[#10a37f] hover:underline"
                            onClick={() => handleActivate(t.id)}
                          >
                            Activate business
                          </button>
                          {t.id !== 1 && (
                            <button
                              type="button"
                              className="text-sm text-red-400 hover:underline"
                              onClick={() => openDeleteModal(t)}
                            >
                              Delete business
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
          {tenants.length === 0 && (
            <p className="py-8 text-center text-[#9ca3af]">No businesses yet</p>
          )}
        </div>
      )}

      <Modal
        open={managerModal !== null}
        onClose={() => setManagerModal(null)}
        title={managerModal?.mode === "edit" ? "Edit master admin" : "Add master admin"}
        footer={
          <>
            <button
              type="button"
              onClick={() => setManagerModal(null)}
              className="flex-1 rounded-lg bg-[#333333] px-4 py-2 text-[#fafaff]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSaveManager}
              disabled={managerSaving}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[#10a37f] px-4 py-2 text-white disabled:opacity-50"
            >
              {managerSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save
            </button>
          </>
        }
      >
        {managerError && (
          <p className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {managerError}
          </p>
        )}
        <div className="space-y-3">
          <input
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] disabled:opacity-60"
            placeholder="Username"
            value={managerForm.username}
            disabled={managerModal?.mode === "edit"}
            onChange={(e) => setManagerForm({ ...managerForm, username: e.target.value })}
          />
          <input
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]"
            type="password"
            placeholder={managerModal?.mode === "edit" ? "New password (optional)" : "Password (min 8 chars)"}
            value={managerForm.password}
            onChange={(e) => setManagerForm({ ...managerForm, password: e.target.value })}
          />
          <input
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]"
            placeholder="Email (optional)"
            value={managerForm.email}
            onChange={(e) => setManagerForm({ ...managerForm, email: e.target.value })}
          />
          <input
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff]"
            placeholder="Full name (optional)"
            value={managerForm.full_name}
            onChange={(e) => setManagerForm({ ...managerForm, full_name: e.target.value })}
          />
          {managerModal?.mode === "edit" && (
            <label className="flex cursor-pointer items-center gap-2 text-sm text-[#fafaff]">
              <input
                type="checkbox"
                checked={managerForm.active}
                onChange={(e) => setManagerForm({ ...managerForm, active: e.target.checked })}
                className="rounded border-[#333]"
              />
              Active
            </label>
          )}
        </div>
      </Modal>

      <Modal
        open={deleteModal !== null}
        onClose={() => setDeleteModal(null)}
        title="Delete business permanently"
        footer={
          <>
            <button
              type="button"
              onClick={() => setDeleteModal(null)}
              className="flex-1 rounded-lg bg-[#333333] px-4 py-2 text-[#fafaff]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleDeleteTenant}
              disabled={
                deleteSaving ||
                confirmSlug.trim().toLowerCase() !== (deleteModal?.slug ?? "").toLowerCase()
              }
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-white hover:bg-red-700 disabled:opacity-50"
            >
              {deleteSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Permanently delete
            </button>
          </>
        }
      >
        {deleteModal && (
          <>
            <p className="mb-4 text-sm text-[#9ca3af]">
              This will permanently remove <strong className="text-[#fafaff]">{deleteModal.name}</strong>{" "}
              and all associated data: staff accounts, customer memberships, support tickets, knowledge
              base documents, chat history for this business, and analytics.
            </p>
            <p className="mb-3 text-sm text-[#fafaff]">
              Type <span className="font-mono text-red-400">{deleteModal.slug || `tenant-${deleteModal.id}`}</span>{" "}
              to confirm:
            </p>
            {deleteError && (
              <p className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                {deleteError}
              </p>
            )}
            <input
              className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 text-[#fafaff] focus:border-red-500 focus:outline-none"
              placeholder="Business slug"
              value={confirmSlug}
              onChange={(e) => setConfirmSlug(e.target.value)}
            />
          </>
        )}
      </Modal>
    </div>
  );
}
