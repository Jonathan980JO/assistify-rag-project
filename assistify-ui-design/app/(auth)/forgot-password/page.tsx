"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CsrfForm } from "@/src/components/CsrfForm";
import { AuthError, AuthInput, AuthLink, AuthPageShell, AuthSubmit } from "@/src/components/AuthPageShell";
import { authFlashMessage } from "@/src/lib/authMessages";
import { appPath } from "@/src/lib/routes";

function ForgotPasswordForm() {
  const params = useSearchParams();
  const error = authFlashMessage(params.get("error"));
  const message = authFlashMessage(params.get("message"));

  return (
    <AuthPageShell title="Forgot password" footer={<AuthLink href={appPath("/login")}>Back to login</AuthLink>}>
      <AuthError message={error} />
      {message && !error ? (
        <div className="mb-4 rounded-md border-l-4 border-[#10a37f] bg-[#10a37f]/20 px-3 py-2 text-center text-sm font-semibold text-[#10a37f]">
          {message}
        </div>
      ) : null}
      <CsrfForm action="/forgot-password">
        <AuthInput name="email" type="email" placeholder="Email address" required />
        <AuthSubmit label="Send reset link" />
      </CsrfForm>
    </AuthPageShell>
  );
}

export default function ForgotPasswordPage() {
  return (
    <Suspense>
      <ForgotPasswordForm />
    </Suspense>
  );
}
