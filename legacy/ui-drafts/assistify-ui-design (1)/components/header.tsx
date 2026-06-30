'use client'

import { Menu, Globe, X } from 'lucide-react'
import { useState } from 'react'

interface HeaderProps {
  language: 'en' | 'ar'
  onLanguageChange: (lang: 'en' | 'ar') => void
  onMenuClick: () => void
}

export function Header({
  language,
  onLanguageChange,
  onMenuClick,
}: HeaderProps) {
  const [showLanguageMenu, setShowLanguageMenu] = useState(false)

  return (
    <header className="border-b border-[#333333] bg-[#232323] px-4 md:px-6 py-4">
      <div className="flex items-center justify-between max-w-6xl mx-auto">
        {/* Left: Hamburger */}
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 hover:bg-[#2b2b2b] rounded transition-colors text-[#fafaff]"
        >
          <Menu size={24} />
        </button>

        {/* Center: App Title */}
        <div className="flex-1 flex justify-center">
          <h1 className="text-2xl font-bold text-[#fafaff]">Assistify</h1>
        </div>

        {/* Right: Language and Exit */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <button
              onClick={() => setShowLanguageMenu(!showLanguageMenu)}
              className="flex items-center gap-2 p-2 hover:bg-[#2b2b2b] rounded transition-colors text-[#fafaff]"
            >
              <Globe size={20} />
              <span className="text-sm font-medium">{language.toUpperCase()}</span>
            </button>
            {showLanguageMenu && (
              <div className="absolute right-0 top-full mt-1 bg-[#2b2b2b] border border-[#333333] rounded shadow-lg z-10">
                <button
                  onClick={() => {
                    onLanguageChange('en')
                    setShowLanguageMenu(false)
                  }}
                  className={`block w-full text-left px-4 py-2 text-sm ${
                    language === 'en'
                      ? 'bg-[#10a37f] text-white'
                      : 'text-[#fafaff] hover:bg-[#333333]'
                  }`}
                >
                  🇺🇸 English
                </button>
                <button
                  onClick={() => {
                    onLanguageChange('ar')
                    setShowLanguageMenu(false)
                  }}
                  className={`block w-full text-left px-4 py-2 text-sm ${
                    language === 'ar'
                      ? 'bg-[#2563eb] text-white'
                      : 'text-[#fafaff] hover:bg-[#333333]'
                  }`}
                >
                  🇸🇦 العربية
                </button>
              </div>
            )}
          </div>
          <button className="p-2 hover:bg-[#2b2b2b] rounded transition-colors text-[#fafaff]">
            <X size={20} />
          </button>
        </div>
      </div>
    </header>
  )
}
