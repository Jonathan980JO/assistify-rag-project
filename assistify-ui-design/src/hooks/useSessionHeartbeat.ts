"use client";

import { useEffect, useRef } from "react";
import { secureFetch } from "@/src/lib/apiClient";

const ACTIVITY_EVENTS = ["mousedown", "keydown", "scroll", "touchstart", "mousemove"] as const;

/**
 * Keeps an actively-used session from silently hitting the server-side idle
 * timeout (which would turn the next mutating request into a 401 -> forced
 * logout, dropping the user's in-progress action).
 *
 * Strategy: track the last time the user interacted with the page. On a fixed
 * interval (well under the server idle timeout), if there was activity since the
 * previous tick, ping a lightweight authenticated endpoint so the server refreshes
 * `last_activity`. A genuinely idle user sends no heartbeat and still expires.
 */
export function useSessionHeartbeat({
  enabled = true,
  intervalMs = 5 * 60 * 1000,
}: {
  enabled?: boolean;
  intervalMs?: number;
} = {}) {
  const lastActivityRef = useRef<number>(Date.now());

  useEffect(() => {
    if (!enabled) return;

    const markActive = () => {
      lastActivityRef.current = Date.now();
    };

    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, markActive, { passive: true });
    }

    const tick = () => {
      // Only keep the session alive while the user is actually present.
      if (Date.now() - lastActivityRef.current > intervalMs) return;
      // secureFetch handles a genuine 401 by redirecting to login.
      void secureFetch("/api/session/heartbeat", { method: "GET" }).catch(() => {});
    };

    const timer = window.setInterval(tick, intervalMs);

    return () => {
      window.clearInterval(timer);
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, markActive);
      }
    };
  }, [enabled, intervalMs]);
}
