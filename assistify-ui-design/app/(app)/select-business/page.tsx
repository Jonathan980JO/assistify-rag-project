"use client";

import { useMemberships } from "@/src/hooks/useMemberships";

export default function SelectBusinessPage() {
  const { memberships, businesses, loading, requestAccess, setActiveTenant } = useMemberships();

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Businesses</h1>
      {loading ? (
        <p>Loading...</p>
      ) : (
        <>
          <section className="mb-8">
            <h2 className="mb-3 font-semibold">Your memberships</h2>
            <ul className="space-y-2">
              {memberships.map((m) => (
                <li key={m.tenant_id} className="flex items-center justify-between rounded border border-[#333] bg-[#2b2b2b] p-3">
                  <span>{m.business_name} ({m.status})</span>
                  {m.status === "active" && (
                    <button type="button" className="text-sm text-[#10a37f]" onClick={() => setActiveTenant(m.tenant_id).catch(() => {})}>Switch</button>
                  )}
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="mb-3 font-semibold">Request access</h2>
            <ul className="space-y-2">
              {businesses.map((b) => (
                <li key={b.id} className="flex items-center justify-between rounded border border-[#333] bg-[#2b2b2b] p-3">
                  <span>{b.name}</span>
                  <button type="button" className="text-sm text-[#10a37f]" onClick={() => requestAccess(b.id).catch(() => {})}>Request</button>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
