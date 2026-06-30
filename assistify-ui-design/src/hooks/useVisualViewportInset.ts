"use client";

import { useEffect, useState } from "react";

/** Bottom inset when the mobile virtual keyboard is open (iOS Safari). */
export function useVisualViewportInset(): number {
  const [bottomInset, setBottomInset] = useState(0);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    const update = () => {
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      setBottomInset(inset);
    };

    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    update();
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);

  return bottomInset;
}