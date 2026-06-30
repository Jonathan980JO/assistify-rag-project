"use client";

import { Loader2 } from "lucide-react";
import { Card } from "@/src/components/ui/Card";
import {
  type KbPipelineStatus,
  KB_PIPELINE_STEPS,
  displayFilename,
  isPipelineBusy,
  stageLabel,
} from "@/src/types/kbPipeline";

function stepIndex(stage?: string): number {
  const key = (stage ?? "").toLowerCase();
  if (key === "uploading") return -1;
  const idx = KB_PIPELINE_STEPS.indexOf(key as (typeof KB_PIPELINE_STEPS)[number]);
  return idx;
}

function StepIndicator({ currentStage }: { currentStage?: string }) {
  const current = stepIndex(currentStage);

  return (
    <div className="flex flex-wrap items-center gap-1 text-xs sm:gap-2">
      {KB_PIPELINE_STEPS.map((step, i) => {
        const label =
          step === "writing" ? "Indexing" : step.charAt(0).toUpperCase() + step.slice(1);
        const isDone = current >= 0 && i < current;
        const isActive = i === current;
        const isFuture = current >= 0 && i > current;

        return (
          <div key={step} className="flex items-center gap-1 sm:gap-2">
            {i > 0 && <span className="text-[#444]">→</span>}
            <span
              className={
                isActive
                  ? "font-medium text-[#10a37f]"
                  : isDone
                    ? "text-[#9ca3af]"
                    : isFuture
                      ? "text-[#555]"
                      : "text-[#555]"
              }
            >
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function KbPipelineStatusPanel({ status }: { status: KbPipelineStatus | null }) {
  if (!status) return null;

  const busy = isPipelineBusy(status.state);
  const failed = status.state === "failed";
  if (!busy && !failed) return null;

  const percent = status.percent ?? 0;
  const hasPercent = (status.total_chunks ?? 0) > 0 || percent > 0;
  const showIndeterminate = busy && !hasPercent;
  const totalChunks = status.total_chunks ?? 0;
  const indexedChunks = Math.min(status.indexed_chunks ?? 0, totalChunks > 0 ? totalChunks : status.indexed_chunks ?? 0);
  const displayPercent = totalChunks > 0
    ? Math.max(0, Math.min(100, Math.round((indexedChunks / totalChunks) * 100)))
    : percent;

  return (
    <Card
      className={`mb-6 p-5 ${
        failed ? "border-red-500/50 bg-red-950/20" : "border-[#10a37f]/30 bg-[#10a37f]/5"
      }`}
    >
      <div className="mb-3 flex items-start gap-3">
        {busy && <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-[#10a37f]" />}
        <div className="min-w-0 flex-1">
          <p className={`font-medium ${failed ? "text-red-400" : "text-[#fafaff]"}`}>
            {stageLabel(status.stage, status.message)}
          </p>
          <p className="mt-0.5 truncate text-sm text-[#9ca3af]">
            {displayFilename(status.filename)}
          </p>
        </div>
      </div>

      {!failed && (
        <>
          <div className="mb-4">
            <StepIndicator currentStage={status.stage} />
          </div>

          <div className="mb-2 h-2 overflow-hidden rounded-full bg-[#333333]">
            {showIndeterminate ? (
              <div className="h-full w-1/3 animate-pulse rounded-full bg-[#10a37f]" />
            ) : (
              <div
                className="h-full rounded-full bg-[#10a37f] transition-all duration-300"
                style={{ width: `${displayPercent}%` }}
              />
            )}
          </div>

          <div className="flex items-center justify-between text-xs text-[#9ca3af]">
            <span>
              {totalChunks > 0
                ? `${indexedChunks} / ${totalChunks} chunks`
                : status.message || ""}
            </span>
            {!showIndeterminate && <span>{displayPercent}%</span>}
          </div>

          {status.warning && (
            <p className="mt-3 text-xs text-[#f6c33c]">{status.warning}</p>
          )}
        </>
      )}

      {failed && status.message && (
        <p className="text-sm text-red-300">{status.message}</p>
      )}
    </Card>
  );
}
