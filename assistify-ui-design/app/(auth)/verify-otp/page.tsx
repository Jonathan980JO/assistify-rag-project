"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CsrfForm } from "@/src/components/CsrfForm";
import { AuthError, AuthInput, AuthPageShell, AuthSubmit } from "@/src/components/AuthPageShell";
import { authFlashMessage } from "@/src/lib/authMessages";

function VerifyOtpForm() {
  const params = useSearchParams();
  const email = params.get("email") ?? "";
  const error = authFlashMessage(params.get("error"));

  return (
    <AuthPageShell title="Verify email" subtitle={`Enter the code sent to ${email || "your email"}`}>
      <AuthError message={error} />
      <CsrfForm action="/verify-otp">
        <input type="hidden" name="email" value={email} />
        <AuthInput name="otp_code" placeholder="6-digit code" required />
        <AuthSubmit label="Verify" />
      </CsrfForm>
    </AuthPageShell>
  );
}

export default function VerifyOtpPage() {
  return (
    <Suspense>
      <VerifyOtpForm />
    </Suspense>
  );
}
