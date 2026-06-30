'use client'

import { useState } from 'react'
import { Save, Lock, Mail, User, Shield, LogOut, Loader2 } from 'lucide-react'

export default function ProfilePage() {
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    fullName: 'Ahmed Khaled',
    username: 'ahmed_khaled',
    email: 'ahmed@example.com',
    role: 'Super Administrator',
    department: 'Engineering',
  })

  const [passwordData, setPasswordData] = useState({
    current: '',
    new: '',
    confirm: '',
  })

  const [notification, setNotification] = useState<{
    type: 'success' | 'error'
    message: string
  } | null>(null)

  const handleProfileSave = async () => {
    setLoading(true)
    try {
      await new Promise((resolve) => setTimeout(resolve, 1000))
      setNotification({
        type: 'success',
        message: 'Profile updated successfully',
      })
      setTimeout(() => setNotification(null), 3000)
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordChange = async () => {
    if (passwordData.new !== passwordData.confirm) {
      setNotification({
        type: 'error',
        message: 'Passwords do not match',
      })
      return
    }

    setLoading(true)
    try {
      await new Promise((resolve) => setTimeout(resolve, 1000))
      setPasswordData({ current: '', new: '', confirm: '' })
      setNotification({
        type: 'success',
        message: 'Password changed successfully',
      })
      setTimeout(() => setNotification(null), 3000)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#fafaff] mb-2">Profile Settings</h1>
        <p className="text-[#9ca3af]">Manage your account and preferences</p>
      </div>

      {/* Notification */}
      {notification && (
        <div
          className={`mb-6 p-4 rounded-lg border ${
            notification.type === 'success'
              ? 'bg-[#10a37f]/10 border-[#10a37f] text-[#10a37f]'
              : 'bg-red-500/10 border-red-500 text-red-400'
          }`}
        >
          {notification.message}
        </div>
      )}

      {/* Profile Information */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-8 mb-8">
        <div className="flex items-start gap-8 mb-8">
          <div className="w-24 h-24 rounded-full bg-gradient-to-br from-[#10a37f] to-[#2563eb] flex items-center justify-center text-2xl font-bold text-white">
            AK
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-bold text-[#fafaff] mb-2">{formData.fullName}</h2>
            <p className="text-[#9ca3af]">{formData.role}</p>
            <div className="flex gap-2 mt-4">
              <span className="px-3 py-1 bg-[#10a37f]/10 text-[#10a37f] rounded-full text-xs font-semibold">
                Active
              </span>
              <span className="px-3 py-1 bg-[#2563eb]/10 text-[#2563eb] rounded-full text-xs font-semibold">
                2FA Enabled
              </span>
            </div>
          </div>
        </div>

        <h3 className="text-lg font-semibold text-[#fafaff] mb-6">Account Information</h3>

        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                Full Name
              </label>
              <div className="flex items-center gap-3 px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg">
                <User className="w-5 h-5 text-[#9ca3af]" />
                <input
                  type="text"
                  value={formData.fullName}
                  onChange={(e) =>
                    setFormData({ ...formData, fullName: e.target.value })
                  }
                  className="flex-1 bg-transparent text-[#fafaff] focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                Username
              </label>
              <div className="flex items-center gap-3 px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg">
                <User className="w-5 h-5 text-[#9ca3af]" />
                <input
                  type="text"
                  value={formData.username}
                  disabled
                  className="flex-1 bg-transparent text-[#9ca3af] focus:outline-none cursor-not-allowed"
                />
              </div>
              <p className="text-xs text-[#9ca3af] mt-1">Username cannot be changed</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-[#9ca3af] mb-2">Email</label>
              <div className="flex items-center gap-3 px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg">
                <Mail className="w-5 h-5 text-[#9ca3af]" />
                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="flex-1 bg-transparent text-[#fafaff] focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-[#9ca3af] mb-2">Role</label>
              <div className="flex items-center gap-3 px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg">
                <Shield className="w-5 h-5 text-[#9ca3af]" />
                <input
                  type="text"
                  value={formData.role}
                  disabled
                  className="flex-1 bg-transparent text-[#9ca3af] focus:outline-none cursor-not-allowed"
                />
              </div>
              <p className="text-xs text-[#9ca3af] mt-1">Contact admin to change role</p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-[#9ca3af] mb-2">Department</label>
            <input
              type="text"
              value={formData.department}
              onChange={(e) =>
                setFormData({ ...formData, department: e.target.value })
              }
              className="w-full px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
            />
          </div>
        </div>

        <button
          onClick={handleProfileSave}
          disabled={loading}
          className="mt-8 flex items-center gap-2 px-6 py-3 bg-[#10a37f] text-white rounded-lg hover:bg-[#0d8a68] disabled:opacity-50 transition-colors font-medium"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="w-5 h-5" />
              Save Changes
            </>
          )}
        </button>
      </div>

      {/* Security Section */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-8 mb-8">
        <h3 className="text-lg font-semibold text-[#fafaff] mb-6 flex items-center gap-2">
          <Lock className="w-5 h-5 text-[#f6c33c]" />
          Security Settings
        </h3>

        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-[#9ca3af] mb-2">
              Current Password
            </label>
            <input
              type="password"
              value={passwordData.current}
              onChange={(e) =>
                setPasswordData({ ...passwordData, current: e.target.value })
              }
              className="w-full px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
              placeholder="Enter current password"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                New Password
              </label>
              <input
                type="password"
                value={passwordData.new}
                onChange={(e) =>
                  setPasswordData({ ...passwordData, new: e.target.value })
                }
                className="w-full px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
                placeholder="Enter new password"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-[#9ca3af] mb-2">
                Confirm Password
              </label>
              <input
                type="password"
                value={passwordData.confirm}
                onChange={(e) =>
                  setPasswordData({ ...passwordData, confirm: e.target.value })
                }
                className="w-full px-4 py-3 bg-[#232323] border border-[#333333] rounded-lg text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f]"
                placeholder="Confirm new password"
              />
            </div>
          </div>

          <button
            onClick={handlePasswordChange}
            disabled={loading}
            className="flex items-center gap-2 px-6 py-3 bg-[#2563eb] text-white rounded-lg hover:bg-[#1d4ed8] disabled:opacity-50 transition-colors font-medium"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Updating...
              </>
            ) : (
              <>
                <Lock className="w-5 h-5" />
                Update Password
              </>
            )}
          </button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-8">
        <h3 className="text-lg font-semibold text-red-400 mb-4">Danger Zone</h3>
        <p className="text-[#9ca3af] mb-6">
          These actions are irreversible. Please be careful.
        </p>
        <button className="flex items-center gap-2 px-6 py-3 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors font-medium">
          <LogOut className="w-5 h-5" />
          Logout from All Devices
        </button>
      </div>
    </div>
  )
}
