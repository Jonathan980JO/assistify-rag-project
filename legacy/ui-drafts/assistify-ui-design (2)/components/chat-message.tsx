'use client'

interface ChatMessageProps {
  message: {
    type: 'user' | 'assistant'
    content: string
  }
  language: 'en' | 'ar'
}

export function ChatMessage({ message, language }: ChatMessageProps) {
  const isUser = message.type === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-xs md:max-w-md lg:max-w-lg px-4 py-3 rounded-2xl text-white text-sm"
          style={{ backgroundColor: '#10a37f' }}
        >
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div
        className="max-w-xs md:max-w-md lg:max-w-lg px-4 py-3 rounded-2xl text-[#232323] text-sm"
        style={{ backgroundColor: '#f6c33c' }}
      >
        {message.content}
      </div>
    </div>
  )
}
