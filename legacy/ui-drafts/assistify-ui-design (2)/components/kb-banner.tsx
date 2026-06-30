'use client'

import { X } from 'lucide-react'

export function KBBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="bg-[#ffe9a0] text-[#f59e0b] px-4 md:px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">📚 Knowledge Base updated. Reindexing...</span>
      </div>
      <button
        onClick={onDismiss}
        className="p-1 hover:bg-[#ffd580] rounded transition-colors"
      >
        <X size={18} />
      </button>
    </div>
  )
}
