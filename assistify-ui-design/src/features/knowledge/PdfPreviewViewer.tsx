"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { FRONTEND_BASE } from "@/src/lib/routes";

type PdfPreviewViewerProps = {
  data: Uint8Array;
  documentKey: string;
};

export function PdfPreviewViewer({ data, documentKey }: PdfPreviewViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;

    container.replaceChildren();
    setLoading(true);
    setError(null);

    const renderPdf = async () => {
      try {
        const pdfjsLib = await import("pdfjs-dist");
        pdfjsLib.GlobalWorkerOptions.workerSrc = `${FRONTEND_BASE}/pdf.worker.min.mjs`;

        const loadingTask = pdfjsLib.getDocument({ data: data.slice() });
        const pdf = await loadingTask.promise;
        if (cancelled) return;

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
          const page = await pdf.getPage(pageNum);
          if (cancelled) return;

          const viewport = page.getViewport({ scale: 1.35 });
          const canvas = document.createElement("canvas");
          canvas.width = Math.floor(viewport.width);
          canvas.height = Math.floor(viewport.height);
          canvas.className = "mx-auto mb-4 block max-w-full rounded border border-[#333] bg-white shadow-sm";

          const context = canvas.getContext("2d");
          if (!context) continue;

          await page.render({ canvasContext: context, viewport, canvas }).promise;
          if (cancelled) return;
          container.appendChild(canvas);
        }
      } catch {
        if (!cancelled) {
          setError("Could not render PDF preview.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void renderPdf();

    return () => {
      cancelled = true;
    };
  }, [data, documentKey]);

  return (
    <div className="relative">
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#1a1a1a]/80 text-[#9ca3af]">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Rendering PDF...
        </div>
      )}
      {error ? (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">{error}</p>
      ) : null}
      <div ref={containerRef} className="max-h-[70vh] overflow-auto p-2" />
    </div>
  );
}
