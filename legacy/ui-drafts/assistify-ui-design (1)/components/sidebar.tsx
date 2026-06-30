'use client'

import { MessageSquare, Plus, Trash2, Edit2 } from 'lucide-react'
import { useState } from 'react'

interface Conversation {
  id: string
  title: string
}

export function Sidebar({ onNewChat }: { onNewChat: () => void }) {
  const [conversations, setConversations] = useState<Conversation[]>([
    { id: '1', title: 'Project Planning' },
    { id: '2', title: 'Code Review Discussion' },
    { id: '3', title: 'Design Feedback' },
  ])
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  return (
    <div className="hidden lg:flex flex-col w-64 bg-[#171717] border-r border-[#333333] h-screen">
      {/* Header */}
      <div className="p-4 border-b border-[#333333]">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 bg-[#10a37f] text-white py-2.5 px-4 rounded-lg hover:bg-[#0d8a6b] transition-colors font-medium text-sm"
        >
          <Plus size={20} />
          New Chat
        </button>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto p-2">
        {conversations.map((conv) => (
          <div
            key={conv.id}
            className="mb-1 relative"
            onMouseEnter={() => setHoveredId(conv.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            <button className="w-full text-left p-3 rounded-lg hover:bg-[#2b2b2b] transition-colors text-[#fafaff] text-sm truncate">
              <div className="flex items-center gap-2">
                <MessageSquare size={16} />
                <span className="truncate">{conv.title}</span>
              </div>
            </button>
            {hoveredId === conv.id && (
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1">
                <button className="p-1.5 hover:bg-[#333333] rounded text-[#9ca3af] hover:text-[#fafaff] transition-colors">
                  <Edit2 size={14} />
                </button>
                <button className="p-1.5 hover:bg-[#333333] rounded text-[#9ca3af] hover:text-[#fafaff] transition-colors">
                  <Trash2 size={14} />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
