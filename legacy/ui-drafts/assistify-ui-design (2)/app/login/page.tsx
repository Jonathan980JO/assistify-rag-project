'use client'

import { useState } from 'react'
import { Lock, Mail, Eye, EyeOff, Globe } from 'lucide-react'
import Link from 'next/link'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      if (email && password) {
        // Redirect to admin dashboard
        window.location.href = '/admin'
      } else {
        setError('Invalid credentials')
      }
    } catch (err) {
      setError('Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = async () => {
    setLoading(true)
    try {
      await new Promise(resolve => setTimeout(resolve, 500))
      window.location.href = '/admin'
    } catch (err) {
      setError('Google login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#232323] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="bg-[#2b2b2b] rounded-lg border border-[#333333] p-8">
          {/* Logo and Title */}
          <div className="text-center mb-8">
            <div className="flex justify-center mb-4">
              <div className="w-12 h-12 bg-[#10a37f] rounded-lg flex items-center justify-center">
                <Lock className="w-6 h-6 text-white" />
              </div>
            </div>
            <h1 className="text-2xl font-bold text-[#10a37f] mb-2">Assistify</h1>
            <p className="text-[#9ca3af]">Sign in to continue</p>
          </div>

          {/* Error Message */}
          {error && (
            <div className="mb-6 p-3 rounded-md bg-red-500/10 border border-red-500/30 text-red-400 text-sm flex items-center gap-2">
              <div className="w-4 h-4 rounded-full bg-red-500" />
              {error}
            </div>
          )}

          {/* Google Login */}
          <button
            onClick={handleGoogleLogin}
            disabled={loading}
            className="w-full mb-6 py-3 px-4 rounded-lg bg-white text-[#232323] font-semibold flex items-center justify-center gap-2 hover:bg-gray-100 transition-colors disabled:opacity-50"
          >
            <Globe className="w-4 h-4" />
            Continue with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-4 mb-6">
            <div className="flex-1 h-px bg-[#333333]" />
            <span className="text-[#9ca3af] text-sm">OR</span>
            <div className="flex-1 h-px bg-[#333333]" />
          </div>

          {/* Email Input */}
          <div className="mb-4">
            <label className="block text-[#fafaff] text-sm font-medium mb-2">
              Email or Username
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-3.5 w-5 h-5 text-[#9ca3af]" />
              <input
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter email or username"
                className="w-full bg-[#171717] border border-[#333333] rounded-lg py-3 pl-10 pr-4 text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f] transition-colors"
              />
            </div>
          </div>

          {/* Password Input */}
          <div className="mb-6">
            <label className="block text-[#fafaff] text-sm font-medium mb-2">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-3.5 w-5 h-5 text-[#9ca3af]" />
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full bg-[#171717] border border-[#333333] rounded-lg py-3 pl-10 pr-10 text-[#fafaff] placeholder-[#9ca3af] focus:outline-none focus:border-[#10a37f] transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-3.5 text-[#9ca3af] hover:text-[#fafaff] transition-colors"
              >
                {showPassword ? (
                  <EyeOff className="w-5 h-5" />
                ) : (
                  <Eye className="w-5 h-5" />
                )}
              </button>
            </div>
          </div>

          {/* Forgot Password */}
          <div className="text-right mb-6">
            <Link
              href="#"
              className="text-[#10a37f] hover:text-[#0e9370] text-sm transition-colors"
            >
              Forgot Password?
            </Link>
          </div>

          {/* Sign In Button */}
          <button
            onClick={handleLogin}
            disabled={loading}
            className="w-full py-3 px-4 rounded-lg bg-[#10a37f] text-white font-semibold hover:bg-[#0e9370] transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Signing in...
              </>
            ) : (
              'Sign In'
            )}
          </button>

          {/* Signup Link */}
          <div className="mt-6 text-center text-[#9ca3af]">
            <span>Don&apos;t have an account? </span>
            <Link href="#" className="text-[#10a37f] hover:text-[#0e9370] transition-colors">
              Create one now
            </Link>
          </div>

          {/* Footer Note */}
          <div className="mt-6 p-3 rounded-md bg-[#10a37f]/10 border border-[#10a37f]/20 text-[#10a37f] text-xs">
            <span className="font-semibold">Demo Tip: </span>Use &quot;Continue with Google&quot; for quick access
          </div>
        </div>
      </div>
    </div>
  )
}
