"use client";

import Link from "next/link";
import { useMemberships } from "@/src/hooks/useMemberships";
import { appPath } from "@/src/lib/routes";

export default function MainPage() {
  const { memberships, loading } = useMemberships();

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Welcome</h1>
      <p className="mb-6 text-[#9ca3af]">Launch the voice chat assistant or manage your businesses.</p>
      <Link href={appPath("/")} className="inline-block rounded-lg bg-[#10a37f] px-6 py-3 font-semibold">
        Launch Chat Assistant
      </Link>
      <div className="mt-8">
        <h2 className="mb-2 font-semibold">Your memberships</h2>
        {loading ? (
          <p className="text-[#9ca3af]">Loading...</p>
        ) : (
          <ul className="space-y-2">
            {memberships.map((m) => (
              <li key={m.tenant_id} className="rounded border border-[#333] bg-[#2b2b2b] px-4 py-2">
                {m.business_name} — {m.status}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
