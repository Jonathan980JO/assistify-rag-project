'use client'

import { useState, useMemo } from 'react'
import {
  BarChart3,
  TrendingUp,
  Users,
  Clock,
  Activity,
  Download,
  Filter,
} from 'lucide-react'

export default function AnalyticsPage() {
  const [dateRange, setDateRange] = useState('7days')

  // Mock data generation
  const chartData = useMemo(() => {
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return days.map((day, i) => ({
      day,
      conversations: Math.floor(Math.random() * 200) + 100,
      users: Math.floor(Math.random() * 50) + 20,
      avgTime: (Math.random() * 2 + 1).toFixed(2),
    }))
  }, [])

  const stats = [
    {
      icon: <BarChart3 className="w-6 h-6" />,
      label: 'Total Queries',
      value: '8,432',
      change: '+12.5%',
      color: 'text-[#10a37f]',
    },
    {
      icon: <TrendingUp className="w-6 h-6" />,
      label: 'Success Rate',
      value: '98.2%',
      change: '+2.1%',
      color: 'text-[#2563eb]',
    },
    {
      icon: <Users className="w-6 h-6" />,
      label: 'Active Users',
      value: '342',
      change: '+8.3%',
      color: 'text-[#f6c33c]',
    },
    {
      icon: <Clock className="w-6 h-6" />,
      label: 'Avg Response',
      value: '1.2s',
      change: '-0.3s',
      color: 'text-[#6c63ff]',
    },
  ]

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-[#fafaff] mb-2">Analytics & Monitoring</h1>
          <p className="text-[#9ca3af]">Track performance metrics and user engagement</p>
        </div>
        <div className="flex gap-3">
          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            className="px-4 py-2 bg-[#2b2b2b] border border-[#333333] rounded-lg text-[#fafaff] focus:outline-none focus:border-[#10a37f]"
          >
            <option value="7days">Last 7 Days</option>
            <option value="30days">Last 30 Days</option>
            <option value="90days">Last 90 Days</option>
            <option value="1year">Last Year</option>
          </select>
          <button className="flex items-center gap-2 px-4 py-2 bg-[#2b2b2b] border border-[#333333] rounded-lg text-[#9ca3af] hover:text-[#fafaff] transition-colors">
            <Download className="w-4 h-4" />
            Export
          </button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat, index) => (
          <div
            key={index}
            className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 hover:border-[#10a37f] transition-colors"
          >
            <div className="flex items-start justify-between mb-4">
              <div className={`p-3 bg-opacity-10 rounded-lg ${stat.color}`}>
                {stat.icon}
              </div>
              <span className="text-xs font-semibold text-[#10a37f]">{stat.change}</span>
            </div>
            <p className="text-[#9ca3af] text-sm mb-1">{stat.label}</p>
            <p className="text-2xl font-bold text-[#fafaff]">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Daily Trend */}
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
          <h2 className="text-lg font-bold text-[#fafaff] mb-6">Daily Trend</h2>
          <div className="space-y-4">
            {chartData.map((data, i) => (
              <div key={i}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm text-[#9ca3af]">{data.day}</span>
                  <span className="text-sm font-medium text-[#fafaff]">
                    {data.conversations} conversations
                  </span>
                </div>
                <div className="h-2 bg-[#333333] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-[#10a37f] to-[#2563eb] rounded-full"
                    style={{
                      width: `${(parseInt(data.conversations) / 300) * 100}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Performance Metrics */}
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
          <h2 className="text-lg font-bold text-[#fafaff] mb-6">Performance Metrics</h2>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm text-[#9ca3af]">API Response Time</span>
                <span className="text-sm font-medium text-[#fafaff]">1.2s</span>
              </div>
              <div className="h-2 bg-[#333333] rounded-full overflow-hidden">
                <div className="h-full w-3/4 bg-[#10a37f] rounded-full" />
              </div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm text-[#9ca3af]">System Uptime</span>
                <span className="text-sm font-medium text-[#fafaff]">99.9%</span>
              </div>
              <div className="h-2 bg-[#333333] rounded-full overflow-hidden">
                <div className="h-full w-11/12 bg-[#10a37f] rounded-full" />
              </div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm text-[#9ca3af]">Cache Hit Rate</span>
                <span className="text-sm font-medium text-[#fafaff]">87.3%</span>
              </div>
              <div className="h-2 bg-[#333333] rounded-full overflow-hidden">
                <div className="h-full w-5/6 bg-[#2563eb] rounded-full" />
              </div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm text-[#9ca3af]">Error Rate</span>
                <span className="text-sm font-medium text-[#fafaff]">0.1%</span>
              </div>
              <div className="h-2 bg-[#333333] rounded-full overflow-hidden">
                <div className="h-full w-1/12 bg-red-500 rounded-full" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* User Engagement */}
      <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6">
        <h2 className="text-lg font-bold text-[#fafaff] mb-6">User Engagement by Role</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            { role: 'Customers', users: 245, engagement: 92 },
            { role: 'Employees', users: 45, engagement: 98 },
            { role: 'Admins', users: 8, engagement: 100 },
          ].map((group, i) => (
            <div key={i} className="bg-[#232323] rounded-lg p-4">
              <p className="text-[#9ca3af] text-sm mb-3">{group.role}</p>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-[#9ca3af]">Active Users</span>
                    <span className="text-lg font-bold text-[#fafaff]">{group.users}</span>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-[#9ca3af]">Engagement</span>
                    <span className="text-lg font-bold text-[#10a37f]">
                      {group.engagement}%
                    </span>
                  </div>
                  <div className="h-2 bg-[#333333] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#10a37f] rounded-full"
                      style={{ width: `${group.engagement}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
