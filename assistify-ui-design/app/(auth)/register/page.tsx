"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CsrfForm } from "@/src/components/CsrfForm";
import { AuthError, AuthInput, AuthLink, AuthPageShell, AuthSubmit } from "@/src/components/AuthPageShell";
import { authFlashMessage } from "@/src/lib/authMessages";
import { appPath } from "@/src/lib/routes";

function RegisterForm() {
  const params = useSearchParams();
  const error = authFlashMessage(params.get("error"));

  return (
    <AuthPageShell title="Create account" footer={<AuthLink href={appPath("/login")}>Back to login</AuthLink>}>
      <AuthError message={error} />
      <CsrfForm action="/register">
        <AuthInput name="full_name" placeholder="Full name" required />
        <AuthInput name="username" placeholder="Username" required />
        <AuthInput name="email" type="email" placeholder="Email" required />
        <AuthInput name="password" type="password" placeholder="Password" required />
        <AuthInput name="confirm_password" type="password" placeholder="Confirm password" required />
        <AuthSubmit label="Register" />
      </CsrfForm>
    </AuthPageShell>
  );
}

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterForm />
    </Suspense>
  );
}
