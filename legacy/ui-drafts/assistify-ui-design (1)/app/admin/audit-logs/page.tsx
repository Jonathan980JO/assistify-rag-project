'use client'

import { useState, useMemo } from 'react'
import { Search, Filter, Eye, Download, Calendar } from 'lucide-react'

interface AuditLog {
  id: string
  timestamp: string
  user: string
  action: string
  resource: string
  changes: string
  ipAddress: string
  status: 'success' | 'failed'
}

const mockLogs: AuditLog[] = [
  {
    id: '1',
    timestamp: '2024-06-21 10:32:15',
    user: 'ahmed_khaled',
    action: 'UPDATE',
    resource: 'User #45',
    changes: 'Role changed from customer to employee',
    ipAddress: '192.168.1.100',
    status: 'success',
  },
  {
    id: '2',
    timestamp: '2024-06-21 09:45:22',
    user: 'sarah_smith',
    action: 'DELETE',
    resource: 'Document #102',
    changes: 'Knowledge base document deleted',
    ipAddress: '192.168.1.105',
    status: 'success',
  },
  {
    id: '3',
    timestamp: '2024-06-21 08:15:40',
    user: 'john_admin',
    action: 'CREATE',
    resource: 'User Account',
    changes: 'New user created: test_user@example.com',
    ipAddress: '192.168.1.110',
    status: 'success',
  },
  {
    id: '4',
    timestamp: '2024-06-21 07:32:10',
    user: 'system',
    action: 'LOGIN_FAILED',
    resource: 'Authentication',
    changes: 'Failed login attempt for admin_test',
    ipAddress: '203.0.113.45',
    status: 'failed',
  },
  {
    id: '5',
    timestamp: '2024-06-20 23:12:05',
    user: 'admin_user',
    action: 'UPDATE',
    resource: 'Knowledge Base',
    changes: '5 documents uploaded to RAG system',
    ipAddress: '192.168.1.120',
    status: 'success',
  },
]

export default function AuditLogsPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [actionFilter, setActionFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null)

  const filteredLogs = useMemo(() => {
    return mockLogs.filter((log) => {
      const matchesSearch =
        log.user.toLowerCase().includes(searchTerm.toLowerCase()) ||
        log.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
        log.resource.toLowerCase().includes(searchTerm.toLowerCase())

      const matchesAction = actionFilter === 'all' || log.action === actionFilter
      const matchesStatus = statusFilter === 'all' || log.status === statusFilter

      return matchesSearch && matchesAction && matchesStatus
    })
  }, [searchTerm, actionFilter, statusFilter])

  const getActionColor = (action: string) => {
    if (action.includes('DELETE')) return 'text-red-400 bg-red-400/10'
    if (action.includes('CREATE')) return 'text-[#10a37f] bg-[#10a37f]/10'
    if (action.includes('UPDATE')) return 'text-[#f6c33c] bg-[#f6c33c]/10'
    return 'text-[#2563eb] bg-[#2563eb]/10'
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#fafaff] mb-2">Audit Logs</h1>
        <p className="text-[#9ca3af]">Track system activity and user actions</p>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="relative lg:col-span-2">
          <Search className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="Search logs..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 bg-[#2b2b2b] border border-[#333333] rounded-lg text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
          />
        </div>

        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="px-4 py-3 bg-[#2b2b2b] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
        >
          <option value="all">All Actions</option>
          <option value="CREATE">Create</option>
          <option value="UPDATE">Update</option>
          <option value="DELETE">Delete</option>
          <option value="LOGIN_FAILED">Login Failed</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-4 py-3 bg-[#2b2b2b] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
        >
          <option value="all">All Status</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {/* Logs Table */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#333333] bg-[#232323]">
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Timestamp
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  User
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Action
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Resource
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Status
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredLogs.map((log) => (
                <tr
                  key={log.id}
                  className="border-b border-[#333333] hover:bg-[#2b2b2b] transition-colors"
                >
                  <td className="px-6 py-4 text-sm text-[#9ca3af] font-mono">
                    {log.timestamp}
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-[#fafaff]">
                    {log.user}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-semibold ${getActionColor(
                        log.action
                      )}`}
                    >
                      {log.action}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-[#9ca3af]">{log.resource}</td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-semibold ${
                        log.status === 'success'
                          ? 'bg-[#10a37f]/20 text-[#10a37f]'
                          : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      {log.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <button
                      onClick={() => setSelectedLog(log)}
                      className="p-2 hover:bg-[#333333] rounded-lg text-[#9ca3af] hover:text-[#10a37f] transition-colors"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 w-full max-w-md max-h-96 overflow-y-auto">
            <h2 className="text-xl font-bold text-[#fafaff] mb-6">Log Details</h2>

            <div className="space-y-4">
              <div>
                <p className="text-xs font-semibold text-[#9ca3af] uppercase mb-1">
                  Timestamp
                </p>
                <p className="text-[#fafaff] font-mono text-sm">{selectedLog.timestamp}</p>
              </div>

              <div>
                <p className="text-xs font-semibold text-[#9ca3af] uppercase mb-1">User</p>
                <p className="text-[#fafaff] text-sm">{selectedLog.user}</p>
              </div>

              <div>
                <p className="text-xs font-semibold text-[#9ca3af] uppercase mb-1">Action</p>
                <p className="text-[#fafaff] text-sm">{selectedLog.action}</p>
              </div>

              <div>
                <p className="text-xs font-semibold text-[#9ca3af] uppercase mb-1">Resource</p>
                <p className="text-[#fafaff] text-sm">{selectedLog.resource}</p>
              </div>

              <div>
                <p className="text-xs font-semibold text-[#9ca3af] uppercase mb-1">Changes</p>
                <p className="text-[#fafaff] text-sm bg-[#232323] p-3 rounded-lg">
                  {selectedLog.changes}
                </p>
              </div>

              <div>
                <p className="text-xs font-semibold text-[#9ca3af] uppercase mb-1">
                  IP Address
                </p>
                <p className="text-[#fafaff] text-sm font-mono">{selectedLog.ipAddress}</p>
              </div>

              <div>
                <p className="text-xs font-semibold text-[#9ca3af] uppercase mb-1">Status</p>
                <p
                  className={`text-sm font-semibold ${
                    selectedLog.status === 'success'
                      ? 'text-[#10a37f]'
                      : 'text-red-400'
                  }`}
                >
                  {selectedLog.status}
                </p>
              </div>
            </div>

            <button
              onClick={() => setSelectedLog(null)}
              className="w-full mt-6 px-4 py-2 bg-[#333333] text-[#fafaff] rounded-lg hover:bg-[#444444] transition-colors font-medium"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
