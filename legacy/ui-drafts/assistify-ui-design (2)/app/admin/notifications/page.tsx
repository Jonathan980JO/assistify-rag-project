'use client'

import { useState } from 'react'
import { Bell, CheckCircle, AlertCircle, Info, Trash2, RefreshCw } from 'lucide-react'

interface Notification {
  id: number
  type: 'success' | 'warning' | 'info'
  title: string
  message: string
  timestamp: string
  read: boolean
}

const initialNotifications: Notification[] = [
  {
    id: 1,
    type: 'success',
    title: 'User Created Successfully',
    message: 'New user "Ahmed_Fateh" has been created with customer role',
    timestamp: '2 minutes ago',
    read: false
  },
  {
    id: 2,
    type: 'warning',
    title: 'High Error Rate Detected',
    message: 'System error rate exceeded 5% in the last hour',
    timestamp: '15 minutes ago',
    read: false
  },
  {
    id: 3,
    type: 'info',
    title: 'Knowledge Base Updated',
    message: 'New documents have been added to the knowledge base',
    timestamp: '1 hour ago',
    read: true
  },
  {
    id: 4,
    type: 'success',
    title: 'Access Request Approved',
    message: 'Customer access request from "skip_otp_test_2274923f" has been approved',
    timestamp: '3 hours ago',
    read: true
  },
  {
    id: 5,
    type: 'info',
    title: 'Daily Report Generated',
    message: 'Your daily system report is ready for download',
    timestamp: '1 day ago',
    read: true
  }
]

const notificationIcons = {
  success: CheckCircle,
  warning: AlertCircle,
  info: Info
}

const notificationColors = {
  success: 'bg-[#10a37f]/10 border-[#10a37f]/30 text-[#10a37f]',
  warning: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400',
  info: 'bg-[#2563eb]/10 border-[#2563eb]/30 text-[#2563eb]'
}

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>(initialNotifications)
  const [filter, setFilter] = useState<'all' | 'unread' | 'success' | 'warning' | 'info'>('all')

  const filteredNotifications = notifications.filter(n => {
    if (filter === 'all') return true
    if (filter === 'unread') return !n.read
    return n.type === filter
  })

  const unreadCount = notifications.filter(n => !n.read).length

  const handleMarkAsRead = (id: number) => {
    setNotifications(notifications.map(n =>
      n.id === id ? { ...n, read: true } : n
    ))
  }

  const handleMarkAllAsRead = () => {
    setNotifications(notifications.map(n => ({ ...n, read: true })))
  }

  const handleDelete = (id: number) => {
    setNotifications(notifications.filter(n => n.id !== id))
  }

  const handleDeleteAll = () => {
    if (window.confirm('Are you sure you want to delete all notifications?')) {
      setNotifications([])
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[#fafaff] flex items-center gap-3 mb-2">
            <Bell className="w-8 h-8 text-[#f6c33c]" />
            Notifications
          </h1>
          <p className="text-[#9ca3af]">
            {unreadCount > 0 ? `You have ${unreadCount} unread notification${unreadCount !== 1 ? 's' : ''}` : 'All caught up!'}
          </p>
        </div>
        <div className="flex gap-2">
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllAsRead}
              className="px-4 py-2 bg-[#10a37f] text-white font-semibold rounded-lg hover:bg-[#0e9370] transition-colors flex items-center gap-2"
            >
              <CheckCircle className="w-4 h-4" />
              Mark All as Read
            </button>
          )}
          <button
            onClick={handleDeleteAll}
            disabled={notifications.length === 0}
            className="px-4 py-2 bg-[#333333] text-[#9ca3af] font-semibold rounded-lg hover:bg-[#444444] transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Trash2 className="w-4 h-4" />
            Clear All
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {(['all', 'unread', 'success', 'warning', 'info'] as const).map((type) => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            className={`px-4 py-2 rounded-lg font-semibold whitespace-nowrap transition-colors ${
              filter === type
                ? 'bg-[#10a37f] text-white'
                : 'bg-[#2b2b2b] text-[#9ca3af] border border-[#333333] hover:border-[#10a37f]'
            }`}
          >
            {type.charAt(0).toUpperCase() + type.slice(1)}
            {type === 'unread' && unreadCount > 0 && ` (${unreadCount})`}
          </button>
        ))}
      </div>

      {/* Notifications List */}
      <div className="space-y-3">
        {filteredNotifications.length === 0 ? (
          <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-12 text-center">
            <div className="flex justify-center mb-4">
              <RefreshCw className="w-12 h-12 text-[#9ca3af] opacity-30" />
            </div>
            <p className="text-[#9ca3af] text-lg">No notifications to show</p>
          </div>
        ) : (
          filteredNotifications.map((notification) => {
            const Icon = notificationIcons[notification.type]
            const colorClass = notificationColors[notification.type]

            return (
              <div
                key={notification.id}
                className={`bg-[#2b2b2b] border border-[#333333] rounded-lg p-4 flex gap-4 transition-all ${
                  !notification.read ? 'border-[#10a37f]/50 bg-[#10a37f]/5' : ''
                }`}
              >
                {/* Icon */}
                <div className={`flex-shrink-0 w-12 h-12 rounded-lg border flex items-center justify-center ${colorClass}`}>
                  <Icon className="w-6 h-6" />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <h3 className={`font-bold ${!notification.read ? 'text-[#fafaff]' : 'text-[#9ca3af]'}`}>
                        {notification.title}
                      </h3>
                      <p className="text-[#9ca3af] text-sm mt-1">
                        {notification.message}
                      </p>
                      <p className="text-[#9ca3af] text-xs mt-2">
                        {notification.timestamp}
                      </p>
                    </div>

                    {/* Status Badge */}
                    {!notification.read && (
                      <div className="w-2 h-2 rounded-full bg-[#10a37f] flex-shrink-0 mt-2" />
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex-shrink-0 flex gap-2">
                  {!notification.read && (
                    <button
                      onClick={() => handleMarkAsRead(notification.id)}
                      className="p-2 hover:bg-[#333333] rounded-lg transition-colors text-[#9ca3af] hover:text-[#10a37f]"
                      title="Mark as read"
                    >
                      <CheckCircle className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(notification.id)}
                    className="p-2 hover:bg-[#333333] rounded-lg transition-colors text-[#9ca3af] hover:text-red-400"
                    title="Delete notification"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 text-center">
          <p className="text-[#9ca3af] text-sm mb-1">Total Notifications</p>
          <p className="text-3xl font-bold text-[#fafaff]">{notifications.length}</p>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 text-center">
          <p className="text-[#9ca3af] text-sm mb-1">Unread</p>
          <p className="text-3xl font-bold text-yellow-500">{unreadCount}</p>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 text-center">
          <p className="text-[#9ca3af] text-sm mb-1">Success</p>
          <p className="text-3xl font-bold text-[#10a37f]">{notifications.filter(n => n.type === 'success').length}</p>
        </div>
        <div className="bg-[#2b2b2b] border border-[#333333] rounded-lg p-6 text-center">
          <p className="text-[#9ca3af] text-sm mb-1">Warnings</p>
          <p className="text-3xl font-bold text-yellow-400">{notifications.filter(n => n.type === 'warning').length}</p>
        </div>
      </div>
    </div>
  )
}
