"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
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

function ResetPasswordForm() {
  const params = useSearchParams();
  const email = params.get("email") ?? "";
  const error = authFlashMessage(params.get("error"));
  const message = authFlashMessage(params.get("message"));

  return (
    <AuthPageShell title="Reset password" subtitle="Create a new secure password">
      <AuthError message={error} />
      <AuthSuccess message={message} />
      <CsrfForm action="/reset-password">
        <input type="hidden" name="email" value={email} />
        <label className="mb-2 block text-sm font-semibold">Verification code</label>
        <AuthInput
          name="otp_code"
          type="text"
          inputMode="numeric"
          pattern="[0-9]{6}"
          maxLength={6}
          placeholder="6-digit code from email"
          required
        />
        <label className="mb-2 block text-sm font-semibold">New password</label>
        <AuthInput name="new_password" type="password" minLength={8} required autoComplete="new-password" />
        <label className="mb-2 block text-sm font-semibold">Confirm password</label>
        <AuthInput name="confirm_password" type="password" minLength={8} required autoComplete="new-password" />
        <AuthSubmit label="Update password" />
      </CsrfForm>
      <p className="mt-4 text-center text-sm">
        <AuthLink href={appPath("/login")}>Back to login</AuthLink>
      </p>
    </AuthPageShell>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordForm />
    </Suspense>
  );
}
