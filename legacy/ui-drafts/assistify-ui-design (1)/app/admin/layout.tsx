'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Users,
  BarChart3,
  Clipboard,
  BookOpen,
  Settings,
  Menu,
  X,
  LogOut,
  MessageSquare,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/admin', icon: LayoutDashboard },
  { name: 'Users', href: '/admin/users', icon: Users },
  { name: 'Analytics', href: '/admin/analytics', icon: BarChart3 },
  { name: 'Audit Logs', href: '/admin/audit-logs', icon: Clipboard },
  { name: 'Knowledge Base', href: '/admin/knowledge-base', icon: BookOpen },
  { name: 'Profile', href: '/admin/profile', icon: Settings },
]

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const pathname = usePathname()

  return (
    <div className="flex h-screen bg-[#232323]">
      {/* Sidebar */}
      <div
        className={`${
          sidebarOpen ? 'w-64' : 'w-0'
        } bg-[#171717] border-r border-[#333333] transition-all duration-300 overflow-hidden flex flex-col`}
      >
        <div className="p-6 border-b border-[#333333]">
          <Link href="/admin" className="flex items-center gap-2">
            <MessageSquare className="w-6 h-6 text-[#10a37f]" />
            <span className="text-xl font-bold text-[#10a37f]">Assistify</span>
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-2">
          {navigation.map((item) => {
            const isActive = pathname === item.href
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-[#10a37f] text-white'
                    : 'text-[#9ca3af] hover:bg-[#2b2b2b] hover:text-[#fafaff]'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="text-sm font-medium">{item.name}</span>
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-[#333333]">
          <button className="w-full flex items-center gap-3 px-4 py-3 rounded-lg text-[#9ca3af] hover:bg-[#2b2b2b] transition-colors">
            <LogOut className="w-5 h-5" />
            <span className="text-sm font-medium">Logout</span>
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <div className="bg-[#2b2b2b] border-b border-[#333333] px-6 py-4 flex items-center justify-between">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 hover:bg-[#444444] rounded-lg text-[#9ca3af] transition-colors"
          >
            {sidebarOpen ? (
              <X className="w-5 h-5" />
            ) : (
              <Menu className="w-5 h-5" />
            )}
          </button>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-medium text-[#fafaff]">Admin User</p>
              <p className="text-xs text-[#9ca3af]">Super Administrator</p>
            </div>
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#10a37f] to-[#2563eb]" />
          </div>
        </div>

        {/* Page Content */}
        <div className="flex-1 overflow-y-auto bg-[#232323]">{children}</div>
      </div>
    </div>
  )
}
