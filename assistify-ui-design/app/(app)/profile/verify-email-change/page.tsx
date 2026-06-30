"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CsrfForm } from "@/src/components/CsrfForm";
import { AuthError, AuthInput, AuthSubmit } from "@/src/components/AuthPageShell";
import { authFlashMessage } from "@/src/lib/authMessages";

function VerifyEmailForm() {
  const params = useSearchParams();
  const newEmail = params.get("new_email") ?? "";
  const error = authFlashMessage(params.get("error"));

  return (
    <div className="max-w-md">
      <h1 className="mb-4 text-2xl font-bold">Verify email change</h1>
      <AuthError message={error} />
      <CsrfForm action="/profile/verify-email-change">
        <input type="hidden" name="new_email" value={newEmail} />
        <AuthInput name="otp_code" placeholder="OTP code" required />
        <AuthSubmit label="Confirm" />
      </CsrfForm>
    </div>
  );
}

export default function VerifyEmailChangePage() {
  return (
    <Suspense>
      <VerifyEmailForm />
    </Suspense>
  );
}
