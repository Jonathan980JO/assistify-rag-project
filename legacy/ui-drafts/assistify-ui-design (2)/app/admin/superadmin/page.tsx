'use client'

import { useState } from 'react'
import { Building2, Users, TrendingUp, Plus, Edit2, Trash2, ChevronDown, Shield } from 'lucide-react'
import Link from 'next/link'

interface Business {
  id: number
  name: string
  slug: string
  status: 'Active' | 'Inactive'
  createdDate: string
  totalUsers: number
  masterAdmins: string
  staffBreakdown: string
}

const initialBusinesses: Business[] = [
  {
    id: 1,
    name: 'Default',
    slug: 'default',
    status: 'Active',
    createdDate: '20/06/2026, 17:13:49',
    totalUsers: 7,
    masterAdmins: '1 master_admin, 2 admins, 1 employees, 3 customers',
    staffBreakdown: 'Pending: 0 | Approved: 3 | Rejected: 0 | Revoked: 0'
  }
]

export default function SuperAdminPage() {
  const [businesses, setBusinesses] = useState<Business[]>(initialBusinesses)
  const [newBusiness, setNewBusiness] = useState({ name: '', slug: '' })
  const [showAddForm, setShowAddForm] = useState(false)
  const [expandedBusiness, setExpandedBusiness] = useState<number | null>(null)

  const handleCreateBusiness = (e: React.FormEvent) => {
    e.preventDefault()
    if (newBusiness.name && newBusiness.slug) {
      const business: Business = {
        id: businesses.length + 1,
        name: newBusiness.name,
        slug: newBusiness.slug,
        status: 'Active',
        createdDate: new Date().toLocaleString(),
        totalUsers: 0,
        masterAdmins: 'Assigning...',
        staffBreakdown: 'Pending: 0 | Approved: 0'
      }
      setBusinesses([...businesses, business])
      setNewBusiness({ name: '', slug: '' })
      setShowAddForm(false)
    }
  }

  const handleDeleteBusiness = (id: number) => {
    if (window.confirm('Are you sure you want to delete this business?')) {
      setBusinesses(businesses.filter(b => b.id !== id))
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-[#10a37f] flex items-center gap-3 mb-2">
          <Shield className="w-8 h-8" />
          Platform Super Admin
        </h1>
        <p className="text-[#9ca3af]">Manage businesses, assign master admins, and monitor the platform</p>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#9ca3af] text-sm mb-1">Businesses</p>
              <p className="text-3xl font-bold text-[#10a37f]">{businesses.length}</p>
            </div>
            <Building2 className="w-12 h-12 text-[#10a37f]/30" />
          </div>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#9ca3af] text-sm mb-1">Total Users</p>
              <p className="text-3xl font-bold text-[#10a37f]">{businesses.reduce((sum, b) => sum + b.totalUsers, 0)}</p>
            </div>
            <Users className="w-12 h-12 text-[#10a37f]/30" />
          </div>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#9ca3af] text-sm mb-1">Active Businesses</p>
              <p className="text-3xl font-bold text-[#10a37f]">{businesses.filter(b => b.status === 'Active').length}</p>
            </div>
            <TrendingUp className="w-12 h-12 text-[#10a37f]/30" />
          </div>
        </div>
      </div>

      {/* Create Business */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
        <h2 className="text-xl font-bold text-[#fafaff] mb-4 flex items-center gap-2">
          <Plus className="w-5 h-5 text-[#10a37f]" />
          Create Business
        </h2>

        {showAddForm ? (
          <form onSubmit={handleCreateBusiness} className="space-y-4">
            <div>
              <label className="block text-[#fafaff] text-sm font-medium mb-2">Business Name</label>
              <input
                type="text"
                value={newBusiness.name}
                onChange={(e) => setNewBusiness({ ...newBusiness, name: e.target.value })}
                placeholder="e.g., Acme Corp"
                className="w-full bg-[#171717] border border-[#333333] rounded-lg py-2 px-4 text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
              />
            </div>
            <div>
              <label className="block text-[#fafaff] text-sm font-medium mb-2">Slug</label>
              <input
                type="text"
                value={newBusiness.slug}
                onChange={(e) => setNewBusiness({ ...newBusiness, slug: e.target.value })}
                placeholder="e.g., acme-corp"
                className="w-full bg-[#171717] border border-[#333333] rounded-lg py-2 px-4 text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
              />
            </div>
            <div className="flex gap-3">
              <button
                type="submit"
                className="px-6 py-2 bg-[#10a37f] text-white font-semibold rounded-lg hover:bg-[#0e9370] transition-colors"
              >
                Create
              </button>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-6 py-2 bg-[#333333] text-[#fafaff] font-semibold rounded-lg hover:bg-[#444444] transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <button
            onClick={() => setShowAddForm(true)}
            className="w-full py-3 px-4 border-2 border-dashed border-[#333333] rounded-lg text-[#10a37f] font-semibold hover:border-[#10a37f] hover:bg-[#10a37f]/5 transition-colors"
          >
            + Add New Business
          </button>
        )}
      </div>

      {/* Businesses List */}
      <div className="space-y-4">
        {businesses.map((business) => (
          <div key={business.id} className="bg-[#2b2b2b] border border-[#333333] rounded-lg overflow-hidden">
            {/* Business Header */}
            <button
              onClick={() => setExpandedBusiness(expandedBusiness === business.id ? null : business.id)}
              className="w-full p-6 flex items-center justify-between hover:bg-[#333333] transition-colors text-left"
            >
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-lg font-bold text-[#fafaff]">{business.name}</h3>
                  <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                    business.status === 'Active'
                      ? 'bg-[#10a37f]/20 text-[#10a37f]'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {business.status}
                  </span>
                </div>
                <p className="text-[#9ca3af] text-sm">Tenant ID: {business.id}</p>
              </div>
              <ChevronDown
                className={`w-5 h-5 text-[#9ca3af] transition-transform ${
                  expandedBusiness === business.id ? 'transform rotate-180' : ''
                }`}
              />
            </button>

            {/* Expanded Content */}
            {expandedBusiness === business.id && (
              <div className="border-t border-[#333333] p-6 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <p className="text-[#9ca3af] text-sm mb-1">Created</p>
                    <p className="text-[#fafaff] font-semibold">{business.createdDate}</p>
                  </div>
                  <div>
                    <p className="text-[#9ca3af] text-sm mb-1">Total Users</p>
                    <p className="text-[#fafaff] font-semibold">{business.totalUsers}</p>
                  </div>
                  <div>
                    <p className="text-[#9ca3af] text-sm mb-1">Master Admin</p>
                    <p className="text-[#fafaff] font-semibold text-sm">{business.masterAdmins}</p>
                  </div>
                  <div>
                    <p className="text-[#9ca3af] text-sm mb-1">Staff Breakdown</p>
                    <p className="text-[#fafaff] font-semibold text-sm">{business.staffBreakdown}</p>
                  </div>
                </div>

                {/* Master Admins Section */}
                <div className="pt-4 border-t border-[#333333]">
                  <h4 className="font-bold text-[#fafaff] mb-3 flex items-center gap-2">
                    <Shield className="w-4 h-4 text-[#10a37f]" />
                    Master Admin (1)
                  </h4>
                  <div className="space-y-2">
                    <div className="bg-[#171717] p-3 rounded-lg flex items-center justify-between">
                      <span className="text-[#fafaff]">ahmed_khaled1</span>
                      <div className="flex gap-2">
                        <button className="px-3 py-1 bg-[#2563eb]/20 text-[#2563eb] text-xs font-semibold rounded hover:bg-[#2563eb]/30 transition-colors">
                          Edit
                        </button>
                        <button className="px-3 py-1 bg-red-500/20 text-red-400 text-xs font-semibold rounded hover:bg-red-500/30 transition-colors">
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-3 pt-4">
                  <button className="flex-1 py-2 px-4 bg-[#10a37f] text-white font-semibold rounded-lg hover:bg-[#0e9370] transition-colors flex items-center justify-center gap-2">
                    <Edit2 className="w-4 h-4" />
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeleteBusiness(business.id)}
                    className="flex-1 py-2 px-4 bg-red-500/20 text-red-400 font-semibold rounded-lg hover:bg-red-500/30 transition-colors flex items-center justify-center gap-2"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer Link */}
      <div className="text-center">
        <Link
          href="/admin"
          className="text-[#10a37f] hover:text-[#0e9370] transition-colors"
        >
          ← Back to Admin Dashboard
        </Link>
      </div>
    </div>
  )
}
