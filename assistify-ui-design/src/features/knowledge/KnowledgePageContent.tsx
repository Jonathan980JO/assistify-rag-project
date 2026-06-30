"use client";

import { useCallback, useState } from "react";
import {
  Download,
  Edit2,
  Eye,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { useKnowledge } from "@/src/hooks/useKnowledge";
import { useProfile } from "@/src/hooks/useProfile";
import { Card } from "@/src/components/ui/Card";
import { Modal } from "@/src/components/ui/Modal";
import { PageHeader } from "@/src/components/ui/PageHeader";
import { SearchInput } from "@/src/components/ui/SearchInput";
import { StatCard } from "@/src/components/ui/StatCard";
import { Toast } from "@/src/components/ui/Toast";
import { KbPipelineStatusPanel } from "@/src/features/knowledge/KbPipelineStatusPanel";
import { PdfPreviewViewer } from "@/src/features/knowledge/PdfPreviewViewer";
import { pipelineStateLabel } from "@/src/types/kbPipeline";

function formatBytes(bytes?: number) {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function KnowledgePageContent({
  title = "Knowledge Base",
  readOnly = false,
}: {
  title?: string;
  readOnly?: boolean;
}) {
  const {
    files,
    pipelineStatus,
    isPipelineBusy,
    loading,
    upload,
    reindexAll,
    reindexFile,
    clearCache,
    remove,
    getFileContent,
    fetchPdfPreviewBytes,
    updateFileContent,
    downloadUrl,
  } = useKnowledge();
  const { profile } = useProfile();

  const businessLabel =
    profile?.tenant_name || (profile?.tenant_id ? `Business #${profile.tenant_id}` : "");

  const [searchTerm, setSearchTerm] = useState("");
  const [uploading, setUploading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [reindexingFile, setReindexingFile] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<{ message: string; variant: "success" | "error" } | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewTitle, setPreviewTitle] = useState("");
  const [previewContent, setPreviewContent] = useState("");
  const [previewPdfBytes, setPreviewPdfBytes] = useState<Uint8Array | null>(null);
  const [previewDocumentKey, setPreviewDocumentKey] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [editFilename, setEditFilename] = useState("");
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  const [cacheNotice, setCacheNotice] = useState<{ message: string; variant: "success" | "error" } | null>(null);

  const resetPreviewPdf = useCallback(() => {
    setPreviewPdfBytes(null);
    setPreviewDocumentKey("");
  }, []);

  const closePreview = useCallback(() => {
    resetPreviewPdf();
    setPreviewOpen(false);
  }, [resetPreviewPdf]);

  const dismissCacheNotice = useCallback(() => setCacheNotice(null), []);
  const dismissActionNotice = useCallback(() => setActionNotice(null), []);

  const handleClearCache = async () => {
    setClearingCache(true);
    try {
      const message = await clearCache();
      setCacheNotice({ message, variant: "success" });
    } catch {
      setCacheNotice({
        message: "Failed to clear cache. Please try again.",
        variant: "error",
      });
    } finally {
      setClearingCache(false);
    }
  };

  const filtered = files.filter((f) =>
    f.displayName.toLowerCase().includes(searchTerm.toLowerCase()) ||
    f.filename.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const actionsDisabled = isPipelineBusy || uploading || reindexing || reindexingFile !== null || clearingCache;
  const statusLabel = pipelineStateLabel(pipelineStatus?.state);
  const indexedChunksTotal =
    pipelineStatus?.collection_chunks ??
    pipelineStatus?.indexed_chunks ??
    files.reduce((sum, f) => sum + (f.indexed_chunks ?? 0), 0);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await upload(file);
    } finally {
      setUploading(false);
    }
  };

  const handleReindexAll = async () => {
    setReindexing(true);
    try {
      await reindexAll();
    } catch {
      setActionNotice({
        message: "Reindex all failed. Please try again.",
        variant: "error",
      });
    } finally {
      setReindexing(false);
    }
  };

  const handleReindexFile = async (filename: string) => {
    setReindexingFile(filename);
    try {
      await reindexFile(filename);
    } catch {
      setActionNotice({
        message: "Reindex failed. Please try again.",
        variant: "error",
      });
    } finally {
      setReindexingFile(null);
    }
  };

  const openPreview = async (storedName: string, displayName: string) => {
    resetPreviewPdf();
    setPreviewTitle(displayName);
    setPreviewContent("");
    setPreviewError(null);
    setPreviewLoading(true);
    setPreviewOpen(true);
    try {
      if (storedName.toLowerCase().endsWith(".pdf")) {
        const bytes = await fetchPdfPreviewBytes(storedName);
        setPreviewPdfBytes(bytes);
        setPreviewDocumentKey(storedName);
      } else {
        const content = await getFileContent(storedName);
        setPreviewContent(content);
      }
    } catch {
      setPreviewError("Could not load preview. The file may have been moved, renamed, or deleted.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const openEdit = async (filename: string) => {
    const content = await getFileContent(filename);
    setEditFilename(filename);
    setEditContent(content);
    setEditOpen(true);
  };

  const saveEdit = async () => {
    setSaving(true);
    try {
      await updateFileContent(editFilename, editContent);
      setEditOpen(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={
          businessLabel
            ? `Managing knowledge base for ${businessLabel}`
            : "Upload and manage knowledge base documents"
        }
      />

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <StatCard icon={<FileText className="h-6 w-6" />} label="Documents" value={String(files.length)} colorClass="text-[#10a37f]" />
        <StatCard
          icon={<Upload className="h-6 w-6" />}
          label="KB Status"
          value={statusLabel}
          colorClass={
            pipelineStatus?.state === "failed"
              ? "text-red-400"
              : isPipelineBusy
                ? "text-[#f6c33c]"
                : "text-[#2563eb]"
          }
        />
        <StatCard
          icon={<FileText className="h-6 w-6" />}
          label="Indexed Chunks"
          value={String(indexedChunksTotal)}
          colorClass="text-[#f6c33c]"
        />
      </div>

      <KbPipelineStatusPanel status={pipelineStatus} />

      {!readOnly && (
        <Card className="mb-8 border-dashed p-8 text-center">
          <Upload className="mx-auto mb-4 h-10 w-10 text-[#10a37f]" />
          <p className="mb-4 text-[#9ca3af]">Upload PDF or TXT documents for the knowledge base</p>
          <label
            className={`inline-flex items-center gap-2 rounded-lg bg-[#10a37f] px-6 py-2 text-sm font-medium text-white hover:bg-[#0d8a68] ${
              actionsDisabled ? "pointer-events-none opacity-50" : "cursor-pointer"
            }`}
          >
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Choose file
            <input
              type="file"
              accept=".pdf,.txt"
              className="hidden"
              disabled={actionsDisabled}
              onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0]).catch(() => {})}
            />
          </label>
          <button
            type="button"
            disabled={actionsDisabled}
            className="ml-3 inline-flex items-center gap-2 rounded-lg border border-[#444] px-4 py-2 text-sm text-[#9ca3af] hover:text-[#fafaff] disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => void handleReindexAll()}
          >
            {reindexing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Reindex all
          </button>
          <button
            type="button"
            disabled={actionsDisabled}
            className="ml-3 inline-flex items-center gap-2 rounded-lg border border-[#444] px-4 py-2 text-sm text-[#9ca3af] hover:text-[#fafaff] disabled:cursor-not-allowed disabled:opacity-50"
            onClick={() => handleClearCache().catch(() => {})}
          >
            {clearingCache ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Clear cache
          </button>
        </Card>
      )}

      <div className="mb-4">
        <SearchInput value={searchTerm} onChange={setSearchTerm} placeholder="Search documents..." />
      </div>

      {loading ? (
        <p className="text-[#9ca3af]">Loading documents...</p>
      ) : (
        <div className="space-y-3">
          {filtered.map((f) => (
            <Card key={f.filename} className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-3">
                <FileText className="h-5 w-5 text-[#10a37f]" />
                <div>
                  <span className="font-medium text-[#fafaff]">{f.displayName}</span>
                  <p className="text-xs text-[#9ca3af]">
                    {formatBytes(f.size)}
                    {typeof f.indexed_chunks === "number" ? ` · ${f.indexed_chunks} chunks` : ""}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void openPreview(f.filename, f.displayName)}
                  className="flex items-center gap-1 rounded-lg bg-[#333333] px-3 py-1.5 text-xs text-[#fafaff] hover:bg-[#444444]"
                >
                  <Eye className="h-3 w-3" /> Preview
                </button>
                <a
                  href={downloadUrl(f.filename)}
                  className="flex items-center gap-1 rounded-lg bg-[#333333] px-3 py-1.5 text-xs text-[#fafaff] hover:bg-[#444444]"
                >
                  <Download className="h-3 w-3" /> Download
                </a>
                {!readOnly && (
                  <>
                    {f.filename.toLowerCase().endsWith(".txt") && (
                      <button
                        type="button"
                        onClick={() => openEdit(f.filename).catch(() => {})}
                        className="flex items-center gap-1 rounded-lg bg-[#2563eb] px-3 py-1.5 text-xs text-white"
                      >
                        <Edit2 className="h-3 w-3" /> Edit
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={actionsDisabled}
                      onClick={() => void handleReindexFile(f.filename)}
                      className="flex items-center gap-1 rounded-lg bg-[#333333] px-3 py-1.5 text-xs text-[#fafaff] disabled:opacity-50"
                    >
                      {reindexingFile === f.filename ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3" />
                      )}{" "}
                      Reindex
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(f.filename).catch(() => {})}
                      disabled={actionsDisabled}
                      className="rounded-lg p-2 text-[#9ca3af] hover:text-red-400 disabled:opacity-50"
                      aria-label="Delete document"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </>
                )}
              </div>
            </Card>
          ))}
          {filtered.length === 0 && (
            <p className="py-8 text-center text-[#9ca3af]">No documents found</p>
          )}
        </div>
      )}

      <Modal
        open={previewOpen}
        onClose={closePreview}
        title={`Preview: ${previewTitle}`}
        size={previewPdfBytes ? "wide" : "default"}
      >
        {previewLoading ? (
          <div className="flex h-48 items-center justify-center text-[#9ca3af]">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Loading preview...
          </div>
        ) : previewError ? (
          <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">{previewError}</p>
        ) : previewPdfBytes ? (
          <PdfPreviewViewer data={previewPdfBytes} documentKey={previewDocumentKey} />
        ) : (
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg bg-[#232323] p-4 text-sm text-[#fafaff]">
            {previewContent || "No preview available"}
          </pre>
        )}
      </Modal>

      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title={`Edit: ${editFilename}`}
        footer={
          <>
            <button type="button" onClick={() => setEditOpen(false)} className="flex-1 rounded-lg bg-[#333333] px-4 py-2 text-[#fafaff]">
              Cancel
            </button>
            <button
              type="button"
              onClick={saveEdit}
              disabled={saving}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-[#10a37f] px-4 py-2 text-white disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save
            </button>
          </>
        }
      >
        <textarea
          className="h-64 w-full rounded-lg border border-[#333333] bg-[#232323] px-4 py-2 font-mono text-sm text-[#fafaff]"
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
        />
      </Modal>

      {cacheNotice && (
        <Toast
          message={cacheNotice.message}
          variant={cacheNotice.variant}
          onDismiss={dismissCacheNotice}
        />
      )}

      {actionNotice && (
        <Toast
          message={actionNotice.message}
          variant={actionNotice.variant}
          onDismiss={dismissActionNotice}
        />
      )}
    </div>
  );
}
