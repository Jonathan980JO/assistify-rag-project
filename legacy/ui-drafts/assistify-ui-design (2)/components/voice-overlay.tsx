'use client'

import { useState, useEffect } from 'react'

interface VoiceOverlayProps {
  onStop: () => void
  language: 'en' | 'ar'
}

export function VoiceOverlay({ onStop, language }: VoiceOverlayProps) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setProgress((prev) => (prev + 10) % 360)
    }, 50)
    return () => clearInterval(interval)
  }, [])

  const states = ['Listening...', 'Processing...', 'Ready']
  const [stateIndex, setStateIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setStateIndex((prev) => (prev + 1) % states.length)
    }, 2000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="flex flex-col items-center gap-8">
        {/* Animated Orb */}
        <div className="relative w-24 h-24">
          {/* Glowing background */}
          <div
            className="absolute inset-0 rounded-full opacity-30 animate-pulse-scale"
            style={{
              background: 'radial-gradient(circle, #6c63ff, transparent)',
            }}
          />

          {/* Main orb */}
          <div
            className="absolute inset-0 rounded-full flex items-center justify-center cursor-pointer hover:opacity-90 transition-opacity"
            style={{
              background: 'radial-gradient(135deg, #7c73ff 0%, #6c63ff 100%)',
              boxShadow: '0 0 40px rgba(108, 99, 255, 0.6)',
            }}
          >
            {/* Mic icon alternative */}
            <div className="text-white text-3xl">🎤</div>
          </div>

          {/* Rotating ring */}
          <svg
            className="absolute inset-0 w-full h-full animate-spin"
            style={{ animationDuration: '3s' }}
            viewBox="0 0 100 100"
          >
            <circle
              cx="50"
              cy="50"
              r="45"
              fill="none"
              stroke="#6c63ff"
              strokeWidth="2"
              opacity="0.3"
              strokeDasharray="282"
              strokeDashoffset="70"
            />
          </svg>
        </div>

        {/* State Text */}
        <div className="text-white text-lg font-medium min-h-6">
          {states[stateIndex]}
        </div>

        {/* Language indicator */}
        <div className="text-[#9ca3af] text-sm">
          {language === 'en' ? '🇺🇸 English' : '🇸🇦 Arabic'}
        </div>

        {/* Stop Button */}
        <button
          onClick={onStop}
          className="mt-4 px-8 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
        >
          Stop
        </button>
      </div>
    </div>
  )
}
