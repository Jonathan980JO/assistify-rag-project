"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Lock, Mail, User } from "lucide-react";
import { useProfile } from "@/src/hooks/useProfile";
import { CsrfForm } from "@/src/components/CsrfForm";
import { AuthError, AuthSuccess } from "@/src/components/AuthPageShell";
import { authFlashMessage } from "@/src/lib/authMessages";
import { apiClient } from "@/src/lib/apiClient";
import { Badge } from "@/src/components/ui/Badge";
import { Card } from "@/src/components/ui/Card";
import { PageHeader } from "@/src/components/ui/PageHeader";

function ProfileContent() {
  const { profile } = useProfile();
  const params = useSearchParams();
  const error = authFlashMessage(params.get("error"));
  const message = authFlashMessage(params.get("message"));
  const [showOldPw, setShowOldPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);

  if (!profile) return null;

  const initials = (profile.full_name || profile.username || "U").slice(0, 2).toUpperCase();

  return (
    <div className="max-w-4xl">
      <PageHeader title="Profile Settings" subtitle="Manage your account and preferences" />

      <AuthError message={error} />
      <AuthSuccess message={message} />

      <Card className="mb-8 p-8">
        <div className="mb-8 flex items-start gap-8">
          <div className="flex h-24 w-24 items-center justify-center rounded-full bg-gradient-to-br from-[#10a37f] to-[#2563eb] text-2xl font-bold text-white">
            {initials}
          </div>
          <div className="flex-1">
            <h2 className="mb-2 text-2xl font-bold text-[#fafaff]">{profile.full_name || profile.username}</h2>
            <p className="capitalize text-[#9ca3af]">{profile.role?.replace(/_/g, " ")}</p>
            <div className="mt-4 flex gap-2">
              <Badge variant="status">{profile.active === false ? "inactive" : "active"}</Badge>
            </div>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex items-center gap-3 rounded-lg bg-[#232323] p-4">
            <User className="h-5 w-5 text-[#10a37f]" />
            <div>
              <p className="text-xs text-[#9ca3af]">Username</p>
              <p className="font-medium">{profile.username}</p>
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-lg bg-[#232323] p-4">
            <Mail className="h-5 w-5 text-[#2563eb]" />
            <div>
              <p className="text-xs text-[#9ca3af]">Email</p>
              <p className="font-medium">{profile.email}</p>
            </div>
          </div>
        </div>
      </Card>

      <Card className="mb-8 p-6">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-[#fafaff]">
          <Mail className="h-5 w-5 text-[#10a37f]" />
          Change email
        </h2>
        <CsrfForm action="/profile/change-email" className="space-y-3">
          <input
            name="new_email"
            type="email"
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-3 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
            placeholder="New email"
            required
          />
          <input
            name="current_password"
            type="password"
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-3 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
            placeholder="Current password"
            required
          />
          <button type="submit" className="rounded-lg bg-[#10a37f] px-6 py-2 text-sm font-medium text-white hover:bg-[#0d8a68]">
            Update email
          </button>
        </CsrfForm>
      </Card>

      <Card className="mb-8 p-6">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-[#fafaff]">
          <Lock className="h-5 w-5 text-[#10a37f]" />
          Change password
        </h2>
        <CsrfForm action="/profile/change-password" className="space-y-3">
          <div className="relative">
            <input
              name="old_password"
              type={showOldPw ? "text" : "password"}
              className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-3 pr-10 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
              placeholder="Current password"
              required
            />
            <button type="button" className="absolute top-3 right-3 text-xs text-[#9ca3af]" onClick={() => setShowOldPw(!showOldPw)}>
              {showOldPw ? "Hide" : "Show"}
            </button>
          </div>
          <div className="relative">
            <input
              name="new_password"
              type={showNewPw ? "text" : "password"}
              className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-3 pr-10 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
              placeholder="New password"
              required
            />
            <button type="button" className="absolute top-3 right-3 text-xs text-[#9ca3af]" onClick={() => setShowNewPw(!showNewPw)}>
              {showNewPw ? "Hide" : "Show"}
            </button>
          </div>
          <input
            name="confirm_password"
            type="password"
            className="w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-3 text-[#fafaff] focus:border-[#10a37f] focus:outline-none"
            placeholder="Confirm new password"
            required
          />
          <button type="submit" className="rounded-lg bg-[#10a37f] px-6 py-2 text-sm font-medium text-white hover:bg-[#0d8a68]">
            Update password
          </button>
        </CsrfForm>
      </Card>

      <Card className="border-red-500/30 p-6">
        <h2 className="mb-2 text-lg font-semibold text-red-400">Danger zone</h2>
        <p className="mb-4 text-sm text-[#9ca3af]">Permanently delete your account. This cannot be undone.</p>
        <button
          type="button"
          className="rounded-lg border border-red-500 px-4 py-2 text-sm text-red-400 hover:bg-red-500/10"
          onClick={() => apiClient.delete("/api/my-account").then(() => { window.location.href = "/logout"; }).catch(() => {})}
        >
          Delete account
        </button>
      </Card>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <Suspense>
      <ProfileContent />
    </Suspense>
  );
}
