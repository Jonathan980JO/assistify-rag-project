"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CsrfForm } from "@/src/components/CsrfForm";
import { AuthError, AuthInput, AuthSubmit } from "@/src/components/AuthPageShell";
import { authFlashMessage } from "@/src/lib/authMessages";

function VerifyPasswordForm() {
  const params = useSearchParams();
  const error = authFlashMessage(params.get("error"));

  return (
    <div className="max-w-md">
      <h1 className="mb-4 text-2xl font-bold">Verify password change</h1>
      <AuthError message={error} />
      <CsrfForm action="/profile/verify-password-change">
        <AuthInput name="otp_code" placeholder="OTP code" required />
        <AuthSubmit label="Confirm" />
      </CsrfForm>
    </div>
  );
}

export default function VerifyPasswordChangePage() {
  return (
    <Suspense>
      <VerifyPasswordForm />
    </Suspense>
  );
}
