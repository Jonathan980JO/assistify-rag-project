'use client'

import { useState, useRef, useEffect } from 'react'
import { Send, Mic, Menu, Globe, X } from 'lucide-react'
import { ChatMessage } from './chat-message'
import { ThinkingIndicator } from './thinking-indicator'
import { VoiceOverlay } from './voice-overlay'
import { Header } from './header'
import { KBBanner } from './kb-banner'

interface Message {
  id: string
  type: 'user' | 'assistant'
  content: string
  language?: 'en' | 'ar'
}

export function ChatArea({ onMenuClick }: { onMenuClick: () => void }) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'user',
      content: 'Can you help me understand React hooks?',
      language: 'en',
    },
    {
      id: '2',
      type: 'assistant',
      content:
        'Of course! React Hooks are functions that let you use state and other React features in functional components. The most commonly used hooks are useState for managing state and useEffect for side effects...',
      language: 'en',
    },
  ])
  const [inputValue, setInputValue] = useState('')
  const [isVoiceActive, setIsVoiceActive] = useState(false)
  const [isThinking, setIsThinking] = useState(false)
  const [language, setLanguage] = useState<'en' | 'ar'>('en')
  const [showBanner, setShowBanner] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = () => {
    if (inputValue.trim()) {
      const userMessage: Message = {
        id: Date.now().toString(),
        type: 'user',
        content: inputValue,
        language,
      }
      setMessages([...messages, userMessage])
      setInputValue('')

      // Simulate thinking
      setIsThinking(true)
      setTimeout(() => {
        setIsThinking(false)
        const assistantMessage: Message = {
          id: (Date.now() + 1).toString(),
          type: 'assistant',
          content:
            'That&apos;s a great question! Let me help you with that. React provides many powerful tools for building interactive UIs efficiently.',
          language,
        }
        setMessages((prev) => [...prev, assistantMessage])
      }, 2000)
    }
  }

  const handleVoiceClick = () => {
    setIsVoiceActive(true)
  }

  const handleVoiceStop = () => {
    setIsVoiceActive(false)
    // Simulate voice input
    setInputValue('What are the best practices for React performance optimization?')
  }

  return (
    <div className="flex-1 flex flex-col bg-[#232323] relative">
      <Header
        language={language}
        onLanguageChange={setLanguage}
        onMenuClick={onMenuClick}
      />

      {showBanner && <KBBanner onDismiss={() => setShowBanner(false)} />}

      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            message={message}
            language={message.language || 'en'}
          />
        ))}
        {isThinking && <ThinkingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-[#333333] bg-[#232323] p-4 md:p-6">
        <div className="max-w-4xl mx-auto">
          <div className="flex gap-3 items-end bg-[#2b2b2b] rounded-lg border border-[#333333] p-3">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={(e) =>
                e.key === 'Enter' && !e.shiftKey && handleSendMessage()
              }
              placeholder="Type your message..."
              className="flex-1 bg-transparent text-[#fafaff] placeholder-[#9ca3af] outline-none text-sm"
            />
            <div className="flex gap-2">
              <button
                onClick={handleVoiceClick}
                className="p-2 hover:bg-[#333333] rounded transition-colors text-[#6c63ff]"
                title="Start voice input"
              >
                <Mic size={20} />
              </button>
              <button
                onClick={handleSendMessage}
                className="p-2 bg-[#10a37f] hover:bg-[#0d8a6b] rounded transition-colors text-white"
                title="Send message"
              >
                <Send size={20} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Voice Overlay */}
      {isVoiceActive && (
        <VoiceOverlay
          onStop={handleVoiceStop}
          language={language}
        />
      )}
    </div>
  )
}
