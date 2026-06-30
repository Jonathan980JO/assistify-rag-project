"use client";

import { CsrfForm } from "@/src/components/CsrfForm";
import { AuthInput, AuthLink, AuthPageShell, AuthSubmit } from "@/src/components/AuthPageShell";
import { appPath } from "@/src/lib/routes";

export default function ChangeUsernamePage() {
  return (
    <AuthPageShell title="Change username" footer={<AuthLink href={appPath("/login")}>Back to login</AuthLink>}>
      <CsrfForm action="/change-username">
        <AuthInput name="email" type="email" placeholder="Account email" required />
        <AuthInput name="password" type="password" placeholder="Password" required />
        <AuthInput name="new_username" placeholder="New username" required />
        <AuthSubmit label="Change username" />
      </CsrfForm>
    </AuthPageShell>
  );
}
