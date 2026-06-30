"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Lock, Mail, Eye, EyeOff } from "lucide-react";
import { PublicTunnelQr } from "@/src/components/PublicTunnelQr";
import { CsrfForm } from "@/src/components/CsrfForm";
import {
  AuthError,
  AuthInput,
  AuthLink,
  AuthPageShell,
  AuthSubmit,
  AuthSuccess,
} from "@/src/components/AuthPageShell";
import { authFlashMessage } from "@/src/lib/authMessages";
import { appPath } from "@/src/lib/routes";

function LoginForm() {
  const params = useSearchParams();
  const error = authFlashMessage(params.get("error"));
  const message = authFlashMessage(params.get("message"));
  const [showPassword, setShowPassword] = useState(false);

  return (
    <AuthPageShell
      title="Assistify"
      subtitle="Sign in to continue"
      footer={
        <>
          <span>Don&apos;t have an account? </span>
          <AuthLink href={appPath("/register")}>Create one now</AuthLink>
          {" · "}
          <AuthLink href={appPath("/forgot-password")}>Forgot password?</AuthLink>
        </>
      }
    >
      <PublicTunnelQr />
      <AuthError message={error} />
      <AuthSuccess message={message} />

      <CsrfForm action="/login">
        <label className="mb-2 block text-sm font-medium text-[#fafaff]">Email or Username</label>
        <AuthInput name="username" type="text" required autoComplete="username" placeholder="Enter email or username" icon={<Mail className="h-5 w-5" />} />

        <label className="mb-2 block text-sm font-medium text-[#fafaff]">Password</label>
        <div className="relative mb-4">
          <Lock className="absolute top-3.5 left-3 h-5 w-5 text-[#9ca3af]" />
          <input
            name="password"
            type={showPassword ? "text" : "password"}
            required
            autoComplete="current-password"
            placeholder="Enter your password"
            className="w-full rounded-lg border border-[#333333] bg-[#171717] py-3 pr-10 pl-10 text-[#fafaff] placeholder-[#9ca3af] focus:border-[#10a37f] focus:outline-none"
          />
          <button
            type="button"
            className="absolute top-3.5 right-3 text-[#9ca3af] hover:text-[#fafaff]"
            onClick={() => setShowPassword(!showPassword)}
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
          </button>
        </div>

        <label className="mb-2 block text-sm font-medium text-[#fafaff]">MFA token (if enabled)</label>
        <AuthInput name="mfa_token" type="text" autoComplete="one-time-code" placeholder="Optional MFA code" />

        <AuthSubmit label="Sign In" />
      </CsrfForm>
    </AuthPageShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
