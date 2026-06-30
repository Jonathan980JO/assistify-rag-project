"use client";

import { useEffect } from "react";

const EVENTS = ["mousedown", "keydown", "scroll", "touchstart"] as const;

export function useInactivityLogout({
  timeoutMs = 30 * 60 * 1000,
  enabled = true,
}: {
  timeoutMs?: number;
  enabled?: boolean;
}) {
  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const reset = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        window.location.href = "/logout";
      }, timeoutMs);
    };

    reset();
    for (const event of EVENTS) {
      window.addEventListener(event, reset, { passive: true });
    }
    return () => {
      if (timer) clearTimeout(timer);
      for (const event of EVENTS) {
        window.removeEventListener(event, reset);
      }
    };
  }, [timeoutMs, enabled]);
}
