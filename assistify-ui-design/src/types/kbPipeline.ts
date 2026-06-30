export type KbPipelineState = "uploading" | "processing" | "ready" | "failed";

export type KbPipelineStage =
  | "uploading"
  | "extracting"
  | "chunking"
  | "embedding"
  | "writing"
  | "activating"
  | "ready"
  | "failed";

export interface KbPipelineStatus {
  state: KbPipelineState;
  stage?: KbPipelineStage | string;
  message?: string;
  filename?: string | null;
  percent?: number;
  indexed_chunks?: number;
  total_chunks?: number;
  collection_chunks?: number;
  stage_timings?: Record<string, number>;
  updated_at?: number;
  proxy_degraded?: boolean;
  /** Non-blocking warning when status polls are repeatedly degraded. */
  warning?: string;
}

export const KB_PIPELINE_STEPS: KbPipelineStage[] = [
  "extracting",
  "chunking",
  "embedding",
  "writing",
  "activating",
];

export const KB_STAGE_LABELS: Record<string, string> = {
  uploading: "Uploading",
  extracting: "Extracting",
  chunking: "Chunking",
  embedding: "Embedding",
  writing: "Indexing",
  activating: "Activating",
  ready: "Ready",
  failed: "Failed",
};

export function isPipelineBusy(state?: string): boolean {
  const s = (state ?? "").toLowerCase();
  return s === "uploading" || s === "processing";
}

export function pipelineStateLabel(state?: string): string {
  const s = (state ?? "").toLowerCase();
  if (s === "ready") return "Ready";
  if (s === "failed") return "Failed";
  if (isPipelineBusy(s)) return "Processing";
  return "Unknown";
}

export function stageLabel(stage?: string, message?: string): string {
  const key = (stage ?? "").toLowerCase();
  if (key && KB_STAGE_LABELS[key]) return KB_STAGE_LABELS[key];
  if (message) return message;
  return "Processing";
}

export function displayFilename(filename?: string | null): string {
  if (!filename || filename === "*") return "All documents";
  return filename;
}
