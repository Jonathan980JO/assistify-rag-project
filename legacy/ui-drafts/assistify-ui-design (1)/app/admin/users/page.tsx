'use client'

import { useState, useCallback } from 'react'
import {
  Plus,
  Search,
  Edit2,
  Trash2,
  ChevronDown,
  Check,
  X,
  Loader2,
} from 'lucide-react'

interface User {
  id: string
  username: string
  email: string
  role: 'admin' | 'employee' | 'customer'
  status: 'active' | 'inactive'
  createdAt: string
}

const mockUsers: User[] = [
  {
    id: '1',
    username: 'ahmed_khaled',
    email: 'ahmed@example.com',
    role: 'admin',
    status: 'active',
    createdAt: '2024-01-15',
  },
  {
    id: '2',
    username: 'sarah_smith',
    email: 'sarah@example.com',
    role: 'employee',
    status: 'active',
    createdAt: '2024-02-20',
  },
  {
    id: '3',
    username: 'john_doe',
    email: 'john@example.com',
    role: 'customer',
    status: 'active',
    createdAt: '2024-03-10',
  },
]

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>(mockUsers)
  const [searchTerm, setSearchTerm] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    role: 'customer' as const,
    password: '',
  })

  const filteredUsers = users.filter((user) =>
    user.username.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.email.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const handleAddUser = useCallback(() => {
    setEditingId(null)
    setFormData({ username: '', email: '', role: 'customer', password: '' })
    setShowModal(true)
  }, [])

  const handleEditUser = useCallback((user: User) => {
    setEditingId(user.id)
    setFormData({
      username: user.username,
      email: user.email,
      role: user.role,
      password: '',
    })
    setShowModal(true)
  }, [])

  const handleSaveUser = useCallback(async () => {
    setLoading(true)
    try {
      await new Promise((resolve) => setTimeout(resolve, 800))

      if (editingId) {
        setUsers((prev) =>
          prev.map((u) =>
            u.id === editingId
              ? {
                  ...u,
                  username: formData.username,
                  email: formData.email,
                  role: formData.role,
                }
              : u
          )
        )
      } else {
        const newUser: User = {
          id: String(users.length + 1),
          username: formData.username,
          email: formData.email,
          role: formData.role,
          status: 'active',
          createdAt: new Date().toISOString().split('T')[0],
        }
        setUsers((prev) => [newUser, ...prev])
      }

      setShowModal(false)
      setFormData({ username: '', email: '', role: 'customer', password: '' })
    } finally {
      setLoading(false)
    }
  }, [editingId, formData, users.length])

  const handleDeleteUser = useCallback((id: string) => {
    if (window.confirm('Are you sure you want to delete this user?')) {
      setUsers((prev) => prev.filter((u) => u.id !== id))
    }
  }, [])

  const handleToggleStatus = useCallback((id: string) => {
    setUsers((prev) =>
      prev.map((u) =>
        u.id === id
          ? { ...u, status: u.status === 'active' ? 'inactive' : 'active' }
          : u
      )
    )
  }, [])

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#fafaff] mb-2">User Management</h1>
        <p className="text-[#9ca3af]">Manage users, roles, and permissions</p>
      </div>

      {/* Controls */}
      <div className="flex flex-col md:flex-row gap-4 mb-8">
        <div className="flex-1 relative">
          <Search className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="Search users..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-3 bg-[#2b2b2b] border border-[#333333] rounded-lg text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
          />
        </div>
        <button
          onClick={handleAddUser}
          className="flex items-center gap-2 px-6 py-3 bg-[#10a37f] text-white rounded-lg hover:bg-[#0d8a68] transition-colors font-medium"
        >
          <Plus className="w-5 h-5" />
          Add User
        </button>
      </div>

      {/* Users Table */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#333333] bg-[#232323]">
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Username
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Email
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Role
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Status
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Created
                </th>
                <th className="px-6 py-4 text-left text-sm font-semibold text-[#9ca3af]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => (
                <tr
                  key={user.id}
                  className="border-b border-[#333333] hover:bg-[#2b2b2b] transition-colors"
                >
                  <td className="px-6 py-4 text-sm font-medium text-[#fafaff]">
                    {user.username}
                  </td>
                  <td className="px-6 py-4 text-sm text-[#9ca3af]">{user.email}</td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium ${
                        user.role === 'admin'
                          ? 'bg-[#2563eb]/20 text-[#2563eb]'
                          : user.role === 'employee'
                            ? 'bg-[#f6c33c]/20 text-[#f6c33c]'
                            : 'bg-[#10a37f]/20 text-[#10a37f]'
                      }`}
                    >
                      {user.role}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <button
                      onClick={() => handleToggleStatus(user.id)}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                        user.status === 'active'
                          ? 'bg-[#10a37f]/20 text-[#10a37f] hover:bg-[#10a37f]/30'
                          : 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                      }`}
                    >
                      {user.status}
                    </button>
                  </td>
                  <td className="px-6 py-4 text-sm text-[#9ca3af]">{user.createdAt}</td>
                  <td className="px-6 py-4 text-sm">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleEditUser(user)}
                        className="p-2 hover:bg-[#333333] rounded-lg text-[#9ca3af] hover:text-[#10a37f] transition-colors"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDeleteUser(user.id)}
                        className="p-2 hover:bg-[#333333] rounded-lg text-[#9ca3af] hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 w-full max-w-md">
            <h2 className="text-xl font-bold text-[#fafaff] mb-6">
              {editingId ? 'Edit User' : 'Create New User'}
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                  Username
                </label>
                <input
                  type="text"
                  value={formData.username}
                  onChange={(e) =>
                    setFormData({ ...formData, username: e.target.value })
                  }
                  className="w-full px-4 py-2 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                  Email
                </label>
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-4 py-2 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                  Role
                </label>
                <select
                  value={formData.role}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      role: e.target.value as 'admin' | 'employee' | 'customer',
                    })
                  }
                  className="w-full px-4 py-2 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
                >
                  <option value="customer">Customer</option>
                  <option value="employee">Employee</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              {!editingId && (
                <div>
                  <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                    Password
                  </label>
                  <input
                    type="password"
                    value={formData.password}
                    onChange={(e) =>
                      setFormData({ ...formData, password: e.target.value })
                    }
                    className="w-full px-4 py-2 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
                  />
                </div>
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowModal(false)}
                className="flex-1 px-4 py-2 bg-[#333333] text-[#fafaff] rounded-lg hover:bg-[#444444] transition-colors font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveUser}
                disabled={loading}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-[#10a37f] text-white rounded-lg hover:bg-[#0d8a68] disabled:opacity-50 transition-colors font-medium"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  'Save User'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
