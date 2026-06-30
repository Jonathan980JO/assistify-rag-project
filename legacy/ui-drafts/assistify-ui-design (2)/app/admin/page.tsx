'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  MessageSquare,
  Users,
  BarChart3,
  TrendingUp,
  RefreshCw,
  FileText,
  Upload,
  Zap,
} from 'lucide-react'

interface StatCard {
  icon: React.ReactNode
  label: string
  value: string | number
  trend?: string
  href?: string
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<StatCard[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Simulate loading stats
    const timer = setTimeout(() => {
      setStats([
        {
          icon: <MessageSquare className="w-6 h-6" />,
          label: 'Total Conversations',
          value: '1,284',
          trend: '+12% this week',
          href: '/admin',
        },
        {
          icon: <Users className="w-6 h-6" />,
          label: 'Active Users',
          value: '342',
          trend: '+8% this week',
          href: '/admin/users',
        },
        {
          icon: <BarChart3 className="w-6 h-6" />,
          label: 'Success Rate',
          value: '98.2%',
          trend: '+2.1% this month',
          href: '/admin/analytics',
        },
        {
          icon: <TrendingUp className="w-6 h-6" />,
          label: 'Avg Response Time',
          value: '1.2s',
          trend: '-0.3s improvement',
          href: '/admin/analytics',
        },
      ])
      setLoading(false)
    }, 500)

    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[#fafaff] mb-2">Admin Dashboard</h1>
        <p className="text-[#9ca3af]">
          Welcome back! Here&apos;s what&apos;s happening with Assistify today.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat, index) => (
          <div
            key={index}
            className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 hover:border-[#10a37f] transition-colors"
          >
            <div className="flex items-start justify-between mb-4">
              <div className="p-3 bg-[#10a37f]/10 rounded-lg text-[#10a37f]">
                {stat.icon}
              </div>
              <RefreshCw className="w-4 h-4 text-[#9ca3af] cursor-pointer hover:text-[#fafaff]" />
            </div>
            <p className="text-[#9ca3af] text-sm mb-1">{stat.label}</p>
            <p className="text-2xl font-bold text-[#fafaff] mb-2">{stat.value}</p>
            {stat.trend && (
              <p className="text-xs text-[#10a37f]">{stat.trend}</p>
            )}
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Recent Activity */}
        <div className="lg:col-span-2 bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
          <h2 className="text-lg font-bold text-[#fafaff] mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <Link
              href="/admin/users"
              className="flex items-center gap-3 p-4 bg-[#232323] rounded-lg hover:bg-[#333333] transition-colors group"
            >
              <Users className="w-5 h-5 text-[#10a37f] group-hover:scale-110 transition-transform" />
              <div className="flex-1">
                <p className="text-[#fafaff] font-medium">Manage Users</p>
                <p className="text-xs text-[#9ca3af]">Create, edit, and manage user accounts</p>
              </div>
            </Link>
            <Link
              href="/admin/knowledge-base"
              className="flex items-center gap-3 p-4 bg-[#232323] rounded-lg hover:bg-[#333333] transition-colors group"
            >
              <FileText className="w-5 h-5 text-[#f6c33c] group-hover:scale-110 transition-transform" />
              <div className="flex-1">
                <p className="text-[#fafaff] font-medium">Knowledge Base</p>
                <p className="text-xs text-[#9ca3af]">Upload and manage RAG documents</p>
              </div>
            </Link>
            <Link
              href="/admin/analytics"
              className="flex items-center gap-3 p-4 bg-[#232323] rounded-lg hover:bg-[#333333] transition-colors group"
            >
              <BarChart3 className="w-5 h-5 text-[#2563eb] group-hover:scale-110 transition-transform" />
              <div className="flex-1">
                <p className="text-[#fafaff] font-medium">View Analytics</p>
                <p className="text-xs text-[#9ca3af]">Check performance metrics and trends</p>
              </div>
            </Link>
          </div>
        </div>

        {/* System Status */}
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
          <h2 className="text-lg font-bold text-[#fafaff] mb-4">System Status</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-[#10a37f] rounded-full" />
                <span className="text-sm text-[#9ca3af]">API Health</span>
              </div>
              <span className="text-xs font-medium text-[#10a37f]">Operational</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-[#10a37f] rounded-full" />
                <span className="text-sm text-[#9ca3af]">Database</span>
              </div>
              <span className="text-xs font-medium text-[#10a37f]">Healthy</span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-[#10a37f] rounded-full" />
                <span className="text-sm text-[#9ca3af]">Cache</span>
              </div>
              <span className="text-xs font-medium text-[#10a37f]">Running</span>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Conversations */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
        <h2 className="text-lg font-bold text-[#fafaff] mb-4">Recent Conversations</h2>
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="flex items-center justify-between p-4 bg-[#232323] rounded-lg hover:bg-[#333333] transition-colors"
            >
              <div className="flex-1">
                <p className="text-[#fafaff] font-medium">User {i} - Technical Support</p>
                <p className="text-xs text-[#9ca3af]">5 messages • 12 min ago</p>
              </div>
              <span className="px-3 py-1 bg-[#10a37f]/10 text-[#10a37f] rounded-full text-xs font-medium">
                Active
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
