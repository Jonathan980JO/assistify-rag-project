"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, secureFetch } from "@/src/lib/apiClient";
import {
  type KbPipelineStatus,
  isPipelineBusy,
} from "@/src/types/kbPipeline";

export interface KnowledgeFile {
  /** Canonical on-disk name used for API calls (may include upload prefix). */
  filename: string;
  /** Human-friendly label for the UI. */
  displayName: string;
  size?: number;
  uploaded_at?: string;
  indexed_chunks?: number;
}

interface RawKnowledgeFile {
  filename?: string;
  name?: string;
  stored_name?: string;
  display_name?: string;
  size?: number;
  modified?: number;
  indexed_chunks?: number;
}

const STORED_PREFIX_RE = /^[0-9a-f]{8}_(.+)$/i;

const POLL_INTERVAL_MS = 1000;
const DEGRADED_WARNING_THRESHOLD = 3;
const DEGRADED_BUSY_MESSAGE = "Knowledge base is busy — still working…";
const DEGRADED_WARNING_MESSAGE =
  "Status updates are delayed — the knowledge base may still be processing.";

function stripStoredPrefix(name: string): string {
  const match = STORED_PREFIX_RE.exec(name);
  return match ? match[1] : name;
}

function normalizeFile(entry: RawKnowledgeFile): KnowledgeFile {
  const stored =
    entry.stored_name ||
    entry.filename ||
    entry.name ||
    "";
  const display =
    entry.display_name ||
    (stored ? stripStoredPrefix(stored) : "") ||
    stored;
  return {
    filename: stored,
    displayName: display,
    size: entry.size,
    uploaded_at: entry.modified ? new Date(entry.modified * 1000).toISOString() : undefined,
    indexed_chunks: entry.indexed_chunks,
  };
}

function parseFileList(data: RawKnowledgeFile[] | { files?: RawKnowledgeFile[] }): KnowledgeFile[] {
  const raw = Array.isArray(data) ? data : data.files ?? [];
  return raw.map(normalizeFile).filter((f) => f.filename);
}

function parseKbStatus(data: Record<string, unknown>): KbPipelineStatus {
  const state = String(data.state ?? "ready").toLowerCase() as KbPipelineStatus["state"];
  return {
    state: ["uploading", "processing", "ready", "failed"].includes(state)
      ? state
      : "ready",
    stage: data.stage as KbPipelineStatus["stage"],
    message: data.message as string | undefined,
    filename: data.filename as string | null | undefined,
    percent: typeof data.percent === "number" ? data.percent : undefined,
    indexed_chunks: typeof data.indexed_chunks === "number" ? data.indexed_chunks : undefined,
    total_chunks: typeof data.total_chunks === "number" ? data.total_chunks : undefined,
    collection_chunks: typeof data.collection_chunks === "number" ? data.collection_chunks : undefined,
    stage_timings: data.stage_timings as Record<string, number> | undefined,
    updated_at: typeof data.updated_at === "number" ? data.updated_at : undefined,
    proxy_degraded: data.proxy_degraded === true,
  };
}

function logKbStatusReceived(status: KbPipelineStatus): void {
  console.info("[KB_STATUS_RECEIVED]", {
    updated_at: status.updated_at,
    state: status.state,
    stage: status.stage,
  });
}

function logKbStatusIgnoredStale(existingUpdatedAt: number, incomingUpdatedAt: number | undefined): void {
  console.info("[KB_STATUS_IGNORED_STALE]", {
    existing_updated_at: existingUpdatedAt,
    incoming_updated_at: incomingUpdatedAt,
  });
}

export function useKnowledge() {
  const [files, setFiles] = useState<KnowledgeFile[]>([]);
  const [pipelineStatus, setPipelineStatus] = useState<KbPipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshRef = useRef<(() => Promise<void>) | null>(null);
  /** Highest backend updated_at applied to the UI — stale polls cannot regress past this. */
  const appliedUpdatedAtRef = useRef<number | undefined>(undefined);
  /** True while a kb_status HTTP request started by the poll loop is in flight. */
  const pollInFlightRef = useRef(false);
  /** Set when READY is observed so late poll completions are ignored. */
  const pollingStoppedRef = useRef(false);
  /**
   * Backend updated_at captured at the moment an upload/reindex starts.
   * While set, a `ready` status whose backend updated_at has NOT advanced
   * past this baseline is treated as a stale prior-job completion and is
   * ignored, so the poll loop keeps running until the active operation
   * actually finishes. Uses backend timestamps only (no client clock).
   */
  const uploadBaselineUpdatedAtRef = useRef<number | undefined>(undefined);
  /** Consecutive proxy_degraded polls while a pipeline operation is active. */
  const degradedPollCountRef = useRef(0);

  const applyDegradedBusyUpdate = useCallback((status: KbPipelineStatus) => {
    degradedPollCountRef.current += 1;
    console.info("[KB_STATUS_IGNORED_DEGRADED]", { message: status.message });

    setPipelineStatus((prev) => {
      if (!prev || !isPipelineBusy(prev.state)) {
        return prev;
      }
      const warning =
        degradedPollCountRef.current >= DEGRADED_WARNING_THRESHOLD
          ? DEGRADED_WARNING_MESSAGE
          : prev.warning;
      return {
        ...prev,
        message: status.message ?? DEGRADED_BUSY_MESSAGE,
        warning,
      };
    });
  }, []);

  const applyKbStatus = useCallback((status: KbPipelineStatus): boolean => {
    logKbStatusReceived(status);

    const incomingUpdatedAt = status.updated_at;
    const existingUpdatedAt = appliedUpdatedAtRef.current;
    const incomingReady = status.state === "ready";

    if (incomingReady) {
      const uploadBaseline = uploadBaselineUpdatedAtRef.current;
      const isStalePriorReady =
        uploadBaseline !== undefined
        && incomingUpdatedAt !== undefined
        && incomingUpdatedAt <= uploadBaseline;
      if (isStalePriorReady) {
        console.info("[KB_STATUS_IGNORED_STALE_READY]", {
          upload_baseline: uploadBaseline,
          incoming_updated_at: incomingUpdatedAt,
        });
        return false;
      }
      if (incomingUpdatedAt !== undefined) {
        appliedUpdatedAtRef.current = incomingUpdatedAt;
      }
      uploadBaselineUpdatedAtRef.current = undefined;
      degradedPollCountRef.current = 0;
      setPipelineStatus(status);
      return true;
    }

    if (status.proxy_degraded) {
      applyDegradedBusyUpdate(status);
      return false;
    }

    if (
      existingUpdatedAt !== undefined
      && incomingUpdatedAt !== undefined
      && incomingUpdatedAt < existingUpdatedAt
    ) {
      logKbStatusIgnoredStale(existingUpdatedAt, incomingUpdatedAt);
      return false;
    }

    if (incomingUpdatedAt !== undefined) {
      appliedUpdatedAtRef.current = incomingUpdatedAt;
    }
    degradedPollCountRef.current = 0;

    setPipelineStatus(status);
    return true;
  }, [applyDegradedBusyUpdate]);

  const stopKbPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const abortPipelineOperation = useCallback(() => {
    stopKbPolling();
    pollingStoppedRef.current = false;
    uploadBaselineUpdatedAtRef.current = undefined;
    degradedPollCountRef.current = 0;
  }, [stopKbPolling]);

  const fetchKbStatus = useCallback(async (): Promise<KbPipelineStatus> => {
    const data = await apiClient.get<Record<string, unknown>>("/api/knowledge/kb_status");
    const status = parseKbStatus(data);
    applyKbStatus(status);
    return status;
  }, [applyKbStatus]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [list, kb] = await Promise.all([
        apiClient.get<RawKnowledgeFile[] | { files?: RawKnowledgeFile[] }>("/api/knowledge/files"),
        apiClient.get<Record<string, unknown>>("/api/knowledge/kb_status"),
      ]);
      setFiles(parseFileList(list));
      applyKbStatus(parseKbStatus(kb));
    } finally {
      setLoading(false);
    }
  }, [applyKbStatus]);

  refreshRef.current = refresh;

  const handlePipelineReady = useCallback(async () => {
    pollingStoppedRef.current = true;
    stopKbPolling();
    await refreshRef.current?.();
  }, [stopKbPolling]);

  const startKbPolling = useCallback(() => {
    stopKbPolling();
    pollingStoppedRef.current = false;

    const poll = async () => {
      if (pollingStoppedRef.current || pollInFlightRef.current) {
        return;
      }

      pollInFlightRef.current = true;
      try {
        const data = await apiClient.get<Record<string, unknown>>("/api/knowledge/kb_status");
        if (pollingStoppedRef.current) {
          return;
        }

        const status = parseKbStatus(data);
        const applied = applyKbStatus(status);
        if (!applied) {
          return;
        }

        if (!isPipelineBusy(status.state)) {
          await handlePipelineReady();
        }
      } catch {
        // keep polling on transient errors
      } finally {
        pollInFlightRef.current = false;
      }
    };

    void poll();
    pollRef.current = setInterval(() => {
      void poll();
    }, POLL_INTERVAL_MS);
  }, [applyKbStatus, handlePipelineReady, stopKbPolling]);

  const beginPipelineOperation = useCallback(
    (optimistic: KbPipelineStatus) => {
      uploadBaselineUpdatedAtRef.current = appliedUpdatedAtRef.current;
      degradedPollCountRef.current = 0;
      setPipelineStatus(optimistic);
      startKbPolling();
    },
    [startKbPolling],
  );

  const runPipelineOperation = useCallback(
    async (optimistic: KbPipelineStatus, execute: () => Promise<void>) => {
      beginPipelineOperation(optimistic);
      try {
        await execute();
      } catch (err) {
        abortPipelineOperation();
        throw err;
      }
    },
    [abortPipelineOperation, beginPipelineOperation],
  );

  const upload = useCallback(
    async (file: File) => {
      await runPipelineOperation(
        {
          state: "uploading",
          stage: "uploading",
          message: "Uploading…",
          filename: file.name,
          percent: 0,
        },
        async () => {
          const form = new FormData();
          form.append("file", file);
          const res = await secureFetch("/proxy/upload_rag", { method: "POST", body: form });
          if (!res.ok) {
            throw new Error("Upload failed");
          }
          await fetchKbStatus();
        },
      );
    },
    [runPipelineOperation, fetchKbStatus],
  );

  const reindexAll = useCallback(async () => {
    await runPipelineOperation(
      {
        state: "processing",
        stage: "extracting",
        message: "Reindexing…",
        filename: "*",
      },
      async () => {
        await apiClient.post("/api/knowledge/reindex-all", {});
      },
    );
  }, [runPipelineOperation]);

  const reindexFile = useCallback(
    async (filename: string) => {
      await runPipelineOperation(
        {
          state: "processing",
          stage: "extracting",
          message: "Reindexing…",
          filename,
        },
        async () => {
          await apiClient.post(
            `/api/knowledge/reindex-file?filename=${encodeURIComponent(filename)}`,
            {},
          );
        },
      );
    },
    [runPipelineOperation],
  );

  const clearCache = useCallback(async () => {
    const data = await apiClient.post<{ message?: string }>("/api/knowledge/clear-cache", {});
    return (
      data?.message ?? "Cache cleared — next chat will use fresh knowledge base data."
    );
  }, []);

  const remove = useCallback(
    async (filename: string) => {
      await apiClient.delete(`/api/knowledge/files/${encodeURIComponent(filename)}`);
      await refresh();
    },
    [refresh],
  );

  const getFileContent = useCallback(async (filename: string) => {
    const data = await apiClient.get<{ content?: string } | string>(
      `/api/knowledge/files/${encodeURIComponent(filename)}`,
    );
    if (typeof data === "string") return data;
    return data.content ?? "";
  }, []);

  const getPdfData = useCallback(async (filename: string) => {
    return apiClient.get<{ bytes_b64?: string; data?: string; base64?: string }>(
      `/api/knowledge/files/${encodeURIComponent(filename)}/pdf-data`,
    );
  }, []);

  const previewUrl = useCallback((filename: string) => {
    return `/api/knowledge/files/${encodeURIComponent(filename)}/preview`;
  }, []);

  const decodePdfBase64 = useCallback((b64: string) => {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }, []);

  /**
   * Fetch PDF via JSON base64 endpoint for in-app canvas rendering.
   * Avoids binary /preview responses that download managers intercept as file downloads.
   */
  const fetchPdfPreviewBytes = useCallback(async (filename: string) => {
    const data = await getPdfData(filename);
    const b64 = data.bytes_b64 ?? data.data ?? data.base64 ?? "";
    if (!b64) {
      throw new Error("Failed to load PDF preview");
    }
    return decodePdfBase64(b64);
  }, [decodePdfBase64, getPdfData]);

  const updateFileContent = useCallback(
    async (filename: string, content: string) => {
      await apiClient.put(`/api/knowledge/files/${encodeURIComponent(filename)}`, { content });
      await refresh();
    },
    [refresh],
  );

  const downloadUrl = useCallback((filename: string) => {
    return `/api/knowledge/files/${encodeURIComponent(filename)}/download`;
  }, []);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      try {
        await refresh();
        if (cancelled) return;
        const status = await fetchKbStatus();
        if (cancelled) return;
        if (isPipelineBusy(status.state)) {
          startKbPolling();
        }
      } catch {
        // Do not start polling on auth/network errors — avoids infinite loops.
      }
    };

    void bootstrap();
    return () => {
      cancelled = true;
      stopKbPolling();
    };
  }, [refresh, fetchKbStatus, startKbPolling, stopKbPolling]);

  const isPipelineBusyState = isPipelineBusy(pipelineStatus?.state);

  return {
    files,
    pipelineStatus,
    isPipelineBusy: isPipelineBusyState,
    loading,
    refresh,
    upload,
    reindexAll,
    reindexFile,
    clearCache,
    remove,
    getFileContent,
    getPdfData,
    previewUrl,
    fetchPdfPreviewBytes,
    updateFileContent,
    downloadUrl,
  };
}
