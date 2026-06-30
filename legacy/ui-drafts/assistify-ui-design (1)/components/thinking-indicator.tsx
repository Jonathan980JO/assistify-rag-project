'use client'

export function ThinkingIndicator() {
  return (
    <div className="flex justify-start">
      <div
        className="px-4 py-3 rounded-2xl text-[#232323] text-sm flex items-center gap-1"
        style={{ backgroundColor: '#f6c33c' }}
      >
        <span>Thinking</span>
        <span className="dot-1 inline-block">.</span>
        <span className="dot-2 inline-block">.</span>
        <span className="dot-3 inline-block">.</span>
      </div>
    </div>
  )
}
