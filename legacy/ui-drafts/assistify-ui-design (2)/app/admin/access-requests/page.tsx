'use client'

import { useState } from 'react'
import { Lock, CheckCircle, XCircle, Clock, Search, Filter } from 'lucide-react'

interface AccessRequest {
  id: number
  username: string
  email: string
  requestDate: string
  status: 'Pending' | 'Approved' | 'Rejected'
  requestType: string
}

const initialRequests: AccessRequest[] = [
  {
    id: 1,
    username: 'john_doe',
    email: 'john@example.com',
    requestDate: '2026-06-20',
    status: 'Pending',
    requestType: 'Premium Access'
  },
  {
    id: 2,
    username: 'jane_smith',
    email: 'jane@example.com',
    requestDate: '2026-06-19',
    status: 'Pending',
    requestType: 'Admin Access'
  }
]

const approvedRequests: AccessRequest[] = [
  {
    id: 3,
    username: 'skip_otp_test_2274923f',
    email: 'skip@example.com',
    requestDate: '2026-06-18',
    status: 'Approved',
    requestType: 'Customer Access'
  },
  {
    id: 4,
    username: 'Ahmed_Fateh',
    email: 'ahmed@example.com',
    requestDate: '2026-06-17',
    status: 'Approved',
    requestType: 'Customer Access'
  },
  {
    id: 5,
    username: 'customer',
    email: 'customer@example.com',
    requestDate: '2026-06-16',
    status: 'Approved',
    requestType: 'Customer Access'
  }
]

export default function AccessRequestsPage() {
  const [pendingRequests, setPendingRequests] = useState<AccessRequest[]>(initialRequests)
  const [approved, setApproved] = useState<AccessRequest[]>(approvedRequests)
  const [searchTerm, setSearchTerm] = useState('')
  const [filterType, setFilterType] = useState('all')

  const handleApprove = (id: number) => {
    const request = pendingRequests.find(r => r.id === id)
    if (request) {
      setPendingRequests(pendingRequests.filter(r => r.id !== id))
      setApproved([...approved, { ...request, status: 'Approved' }])
    }
  }

  const handleReject = (id: number) => {
    setPendingRequests(pendingRequests.filter(r => r.id !== id))
  }

  const handleRevokeAccess = (id: number) => {
    setApproved(approved.filter(r => r.id !== id))
  }

  const filteredPending = pendingRequests.filter(r =>
    (r.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
     r.email.toLowerCase().includes(searchTerm.toLowerCase())) &&
    (filterType === 'all' || r.requestType === filterType)
  )

  const filteredApproved = approved.filter(r =>
    (r.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
     r.email.toLowerCase().includes(searchTerm.toLowerCase())) &&
    (filterType === 'all' || r.requestType === filterType)
  )

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-[#10a37f] flex items-center gap-3 mb-2">
          <Lock className="w-8 h-8" />
          Customer Access Requests
        </h1>
        <p className="text-[#9ca3af]">Manage and approve customer access requests</p>
      </div>

      {/* Search and Filter */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-3 w-5 h-5 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="Search by username or email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#2b2b2b] border border-[#333333] rounded-lg py-3 pl-12 pr-4 text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-4 top-3 w-5 h-5 text-[#9ca3af]" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-[#2b2b2b] border border-[#333333] rounded-lg py-3 pl-12 pr-4 text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
          >
            <option value="all">All Request Types</option>
            <option value="Premium Access">Premium Access</option>
            <option value="Admin Access">Admin Access</option>
            <option value="Customer Access">Customer Access</option>
          </select>
        </div>
      </div>

      {/* Pending Requests */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
        <h2 className="text-2xl font-bold text-[#fafaff] mb-4 flex items-center gap-2">
          <Clock className="w-6 h-6 text-yellow-500" />
          Pending Requests ({filteredPending.length})
        </h2>

        {filteredPending.length === 0 ? (
          <p className="text-[#9ca3af] py-8 text-center">No pending requests</p>
        ) : (
          <div className="space-y-3">
            {filteredPending.map((request) => (
              <div
                key={request.id}
                className="bg-[#171717] border border-[#333333] rounded-lg p-4 flex items-center justify-between hover:border-[#444444] transition-colors"
              >
                <div className="flex-1">
                  <p className="font-semibold text-[#fafaff]">{request.username}</p>
                  <p className="text-[#9ca3af] text-sm">{request.email}</p>
                  <p className="text-[#9ca3af] text-xs mt-1">{request.requestDate}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-3 py-1 bg-yellow-500/20 text-yellow-400 text-xs font-semibold rounded">
                    {request.requestType}
                  </span>
                </div>
                <div className="flex gap-3 ml-4">
                  <button
                    onClick={() => handleApprove(request.id)}
                    className="px-4 py-2 bg-[#10a37f] text-white font-semibold rounded-lg hover:bg-[#0e9370] transition-colors flex items-center gap-2"
                  >
                    <CheckCircle className="w-4 h-4" />
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(request.id)}
                    className="px-4 py-2 bg-red-500/20 text-red-400 font-semibold rounded-lg hover:bg-red-500/30 transition-colors flex items-center gap-2"
                  >
                    <XCircle className="w-4 h-4" />
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Approved Customers */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
        <h2 className="text-2xl font-bold text-[#fafaff] mb-4 flex items-center gap-2">
          <CheckCircle className="w-6 h-6 text-[#10a37f]" />
          Approved Customers ({filteredApproved.length})
        </h2>

        <div className="space-y-3">
          {filteredApproved.map((request) => (
            <div
              key={request.id}
              className="bg-[#171717] border border-[#333333] rounded-lg p-4 flex items-center justify-between hover:border-[#444444] transition-colors"
            >
              <div className="flex-1">
                <p className="font-semibold text-[#fafaff]">{request.username}</p>
                <p className="text-[#9ca3af] text-sm">{request.email}</p>
                <p className="text-[#9ca3af] text-xs mt-1">Approved on {request.requestDate}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="px-3 py-1 bg-[#10a37f]/20 text-[#10a37f] text-xs font-semibold rounded">
                  {request.requestType}
                </span>
              </div>
              <button
                onClick={() => handleRevokeAccess(request.id)}
                className="ml-4 px-4 py-2 bg-red-500/20 text-red-400 font-semibold rounded-lg hover:bg-red-500/30 transition-colors"
              >
                Revoke Access
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 text-center">
          <p className="text-[#9ca3af] text-sm mb-1">Pending Approvals</p>
          <p className="text-3xl font-bold text-yellow-500">{pendingRequests.length}</p>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 text-center">
          <p className="text-[#9ca3af] text-sm mb-1">Total Approved</p>
          <p className="text-3xl font-bold text-[#10a37f]">{approved.length}</p>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 text-center">
          <p className="text-[#9ca3af] text-sm mb-1">Approval Rate</p>
          <p className="text-3xl font-bold text-[#2563eb]">
            {approved.length + pendingRequests.length > 0
              ? Math.round((approved.length / (approved.length + pendingRequests.length)) * 100)
              : 0}%
          </p>
        </div>
      </div>
    </div>
  )
}
