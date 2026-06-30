"use client";

import { useState } from "react";
import { Eye } from "lucide-react";
import { useAuditLogs } from "@/src/hooks/useAuditLogs";
import { DataTable, DataTableCell, DataTableRow } from "@/src/components/ui/DataTable";
import { Modal } from "@/src/components/ui/Modal";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { SearchInput } from "@/src/components/ui/SearchInput";

export function AuditLogsPageContent() {
  const { logs, loading } = useAuditLogs();
  const [searchTerm, setSearchTerm] = useState("");
  const [selected, setSelected] = useState<(typeof logs)[0] | null>(null);

  const filtered = logs.filter(
    (log) =>
      log.username?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.action?.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  return (
    <div>
      <PageHeader title="Audit Logs" subtitle="Searchable audit trail of system actions" />

      <div className="mb-8">
        <SearchInput value={searchTerm} onChange={setSearchTerm} placeholder="Search by user or action..." />
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading audit logs...</p>
      ) : (
        <DataTable
          headers={["User", "Action", "When", "Details"]}
          isEmpty={filtered.length === 0}
          emptyMessage="No audit logs found"
        >
          {filtered.map((log) => (
            <DataTableRow key={log.id}>
              <DataTableCell className="font-medium">{log.username}</DataTableCell>
              <DataTableCell className="text-[#9ca3af]">{log.action}</DataTableCell>
              <DataTableCell className="text-[#9ca3af]">{log.created_at || log.timestamp}</DataTableCell>
              <DataTableCell>
                <button
                  type="button"
                  onClick={() => setSelected(log)}
                  className="flex items-center gap-1 rounded-lg p-2 text-[#9ca3af] transition-colors hover:bg-[#333333] hover:text-[#10a37f]"
                >
                  <Eye className="h-4 w-4" />
                  View
                </button>
              </DataTableCell>
            </DataTableRow>
          ))}
        </DataTable>
      )}

      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title="Audit Log Details"
        footer={
          <button
            type="button"
            onClick={() => setSelected(null)}
            className="flex-1 rounded-lg bg-[#333333] px-4 py-2 font-medium text-[#fafaff]"
          >
            Close
          </button>
        }
      >
        {selected && (
          <div className="space-y-3 text-sm">
            <p><span className="text-[#9ca3af]">User:</span> {selected.username}</p>
            <p><span className="text-[#9ca3af]">Action:</span> {selected.action}</p>
            <p><span className="text-[#9ca3af]">Old value:</span> {selected.old_value || "—"}</p>
            <p><span className="text-[#9ca3af]">New value:</span> {selected.new_value || "—"}</p>
            <p><span className="text-[#9ca3af]">When:</span> {selected.created_at || selected.timestamp}</p>
          </div>
        )}
      </Modal>
    </div>
  );
}
