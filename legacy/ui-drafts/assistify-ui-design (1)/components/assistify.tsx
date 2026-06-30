'use client'

import { useState } from 'react'
import { Sidebar } from './sidebar'
import { ChatArea } from './chat-area'

export function Assistify() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleNewChat = () => {
    // Reset chat
    setSidebarOpen(false)
  }

  return (
    <div className="flex h-screen bg-[#232323]">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 lg:hidden z-40"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`fixed lg:static inset-y-0 left-0 z-50 transition-transform duration-300 lg:transition-none ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <Sidebar onNewChat={handleNewChat} />
      </div>

      {/* Chat Area */}
      <ChatArea
        onMenuClick={() => setSidebarOpen(!sidebarOpen)}
      />
    </div>
  )
}
