"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";

type PublicTunnelInfo = {
  active: boolean;
  guest_chat_url?: string;
  provider?: string;
};

const POLL_MS = 5000;

export function PublicTunnelQr() {
  const [chatUrl, setChatUrl] = useState<string | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [provider, setProvider] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const host = window.location.hostname;
    const isLocalLogin = host === "localhost" || host === "127.0.0.1";
    if (!isLocalLogin) return;

    async function load() {
      try {
        const res = await fetch("/api/public-tunnel", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as PublicTunnelInfo;
        if (cancelled || !data.active || !data.guest_chat_url) {
          if (!cancelled && !data.active) {
            setChatUrl(null);
            setQrDataUrl(null);
            setProvider(null);
          }
          return;
        }

        const url = await QRCode.toDataURL(data.guest_chat_url, {
          margin: 1,
          width: 200,
          color: { dark: "#171717", light: "#ffffff" },
        });
        if (cancelled) return;
        setChatUrl(data.guest_chat_url);
        setProvider(data.provider ?? null);
        setQrDataUrl(url);
      } catch {
        /* tunnel not active */
      }
    }

    void load();
    const timer = setInterval(() => {
      void load();
    }, POLL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (!chatUrl || !qrDataUrl) return null;

  return (
    <div className="mb-6 rounded-xl border border-[#10a37f]/35 bg-[#10a37f]/10 p-4 text-center">
      <p className="mb-1 text-sm font-semibold text-[#10a37f]">Open guest chat on your phone</p>
      <p className="mb-3 text-xs text-[#9ca3af]">
        Scan to chat — no sign-in required{provider ? ` (${provider})` : ""}
      </p>
      <img
        src={qrDataUrl}
        alt="QR code for public Assistify guest chat URL"
        className="mx-auto rounded-lg bg-white p-2"
        width={200}
        height={200}
      />
      <p className="mt-3 break-all text-xs text-[#9ca3af]">{chatUrl}</p>
    </div>
  );
}
