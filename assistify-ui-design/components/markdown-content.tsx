"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

type ParsedPipeTable = {
  headers: string[];
  rows: string[][];
  note?: string;
};

const MERGED_HEADER_CELL_RE =
  /^(Fee|Amount|Term|Notes|Item|Product|Plan|Tier|Feature|Service|Type)\s+(.+)$/i;

/** Fee value glued to the next row label (e.g. "Free Instant transfer"). */
const FEE_CELL_WITH_NEXT_ROW_RE =
  /^(Free|\d+(?:\.\d+)?%(?:\s*\([^)]+\))?|\$\d[\d,]*(?:\.\d+)?(?:\s+outgoing)?(?:\s*\/\s*day)?)\s+([A-Z][a-z].*)$/i;

const TRAILING_NOTE_RE = /^(.{1,80}?)\s+([A-Z][a-z][\s\S]{24,})$/;

function isLikelyTableNote(text: string): boolean {
  return (
    /\b(may be|can be reviewed|on request|subject to|disclaimer)\b/i.test(text) ||
    (/^\s*limits\b/i.test(text) && text.length > 30)
  );
}

function escapeGfmCell(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/\n/g, " ").trim();
}

function splitPipeCells(raw: string): string[] {
  return raw
    .split("|")
    .map((cell) => cell.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

function looksLikePipeTable(block: string): boolean {
  const pipeCount = (block.match(/\|/g) ?? []).length;
  if (pipeCount < 5) return false;
  const cells = splitPipeCells(block);
  return cells.length >= 6;
}

function isHeaderCell(cell: string): boolean {
  if (/\$\d/.test(cell) || /\d+\s*-\s*\d+\s*business/i.test(cell) || /^\d+(?:\.\d+)?%/.test(cell)) {
    return false;
  }
  if (/^(?:ACH|Instant|Domestic|Mobile|Peer|Same business day|Held \d)/i.test(cell)) return false;
  return cell.length <= 40;
}

function detectColumnCount(cells: string[]): number {
  const expanded = expandMergedCells(cells);
  for (const n of [4, 3, 5, 6, 2]) {
    if (expanded.length <= n) continue;
    const remainder = expanded.length - n;
    if (remainder < n || remainder % n !== 0) continue;
    const headers = expanded.slice(0, n);
    if (!headers.every(isHeaderCell)) continue;
    return n;
  }
  return 0;
}

function expandMergedCells(cells: string[]): string[] {
  const expanded: string[] = [];
  for (const cell of cells) {
    const headerSplit = cell.match(MERGED_HEADER_CELL_RE);
    if (headerSplit?.[1] && headerSplit[2]) {
      expanded.push(headerSplit[1].trim(), headerSplit[2].trim());
      continue;
    }
    const feeSplit = cell.match(FEE_CELL_WITH_NEXT_ROW_RE);
    if (feeSplit?.[1] && feeSplit[2] && !isLikelyTableNote(feeSplit[2])) {
      expanded.push(feeSplit[1].trim(), feeSplit[2].trim());
      continue;
    }
    expanded.push(cell);
  }
  return expanded;
}

function extractTrailingNote(lastCell: string): { cell: string; note?: string } {
  const match = lastCell.match(TRAILING_NOTE_RE);
  if (!match?.[1] || !match[2]) return { cell: lastCell };
  const value = match[1].trim();
  const note = match[2].trim();
  if (value.length > 60) return { cell: lastCell };
  return { cell: value, note };
}

function inferHeaderColumnCount(expanded: string[]): number {
  for (let idx = 0; idx < Math.min(expanded.length, 8); idx++) {
    if (/^Fee$/i.test(expanded[idx] ?? "")) return idx + 1;
  }
  return detectColumnCount(expanded);
}

function parsePipeCellsToTable(cells: string[]): ParsedPipeTable | null {
  if (cells.length < 6) return null;
  let note: string | undefined;

  const lastRawIdx = cells.length - 1;
  const { cell: fixedLastCell, note: rawNote } = extractTrailingNote(cells[lastRawIdx] ?? "");
  const normalizedCells = [...cells.slice(0, lastRawIdx), fixedLastCell];
  note = rawNote;

  const expanded = expandMergedCells(normalizedCells);

  const columnCount = inferHeaderColumnCount(expanded);
  if (columnCount < 2 || expanded.length <= columnCount) return null;

  let body = expanded.slice(columnCount);

  if (body.length % columnCount !== 0) {
    const orphan = body[body.length - 1];
    if (orphan && isLikelyTableNote(orphan)) {
      note = note ? `${note} ${orphan}` : orphan;
      body = body.slice(0, -1);
    }
  }

  if (body.length % columnCount !== 0) {
    return null;
  }

  const lastRowStart = body.length - columnCount;
  const lastRow = body.slice(lastRowStart);
  const { cell: fixedFeeCell, note: trailingNote } = extractTrailingNote(lastRow[columnCount - 1] ?? "");
  if (trailingNote) {
    lastRow[columnCount - 1] = fixedFeeCell;
    body = [...body.slice(0, lastRowStart), ...lastRow];
    note = note ? `${note} ${trailingNote}` : trailingNote;
  }

  const rows: string[][] = [];
  for (let i = 0; i < body.length; i += columnCount) {
    rows.push(body.slice(i, i + columnCount));
  }
  if (!rows.length) return null;

  return {
    headers: expanded.slice(0, columnCount),
    rows,
    note,
  };
}

function parseLinePipeTable(lines: string[]): ParsedPipeTable | null {
  const rowCells = lines.map((line) => splitPipeCells(line));
  const columnCount = rowCells[0]?.length ?? 0;
  if (columnCount < 2) return null;
  if (!rowCells.every((row) => row.length === columnCount)) return null;

  const headers = rowCells[0];
  const rows = rowCells.slice(1);
  if (!rows.length) return null;

  const lastRow = rows[rows.length - 1];
  const { cell: fixedLastCell, note } = extractTrailingNote(lastRow[columnCount - 1] ?? "");
  if (note) {
    lastRow[columnCount - 1] = fixedLastCell;
  }

  return { headers, rows, note };
}

function parseMashedPipeTable(line: string): ParsedPipeTable | null {
  return parsePipeCellsToTable(splitPipeCells(line));
}

function toGfmTable(table: ParsedPipeTable): string {
  const headerRow = `| ${table.headers.map(escapeGfmCell).join(" | ")} |`;
  const separatorRow = `| ${table.headers.map(() => "---").join(" | ")} |`;
  const bodyRows = table.rows.map((row) => `| ${row.map(escapeGfmCell).join(" | ")} |`);
  const parts = [headerRow, separatorRow, ...bodyRows];
  if (table.note) parts.push("", table.note);
  return parts.join("\n");
}

/** Rewrite RAG pipe-table blobs into GFM so remark-gfm renders styled tables. */
export function formatPipeDelimitedTables(content: string): string {
  const blocks = content.split(/\n\n+/);
  const formatted = blocks.map((block) => {
    const trimmed = block.trim();
    if (!trimmed || !looksLikePipeTable(trimmed)) return block;

    const lines = trimmed.split("\n").map((line) => line.trim()).filter(Boolean);
    const parsed =
      lines.length === 1
        ? parseMashedPipeTable(lines[0]!)
        : lines.every((line) => (line.match(/\|/g) ?? []).length >= 2)
          ? parseLinePipeTable(lines)
          : parseMashedPipeTable(trimmed.replace(/\n+/g, " "));

    return parsed ? toGfmTable(parsed) : block;
  });

  return formatted.join("\n\n");
}

/** Normalize common LLM markdown quirks so lists and headings render correctly. */
export function normalizeMarkdown(content: string): string {
  let text = content.replace(/\r\n/g, "\n").trim();
  if (!text) return text;

  // Strip raw document-header separator lines (===, ---, ~~~) from RAG chunks
  text = text.replace(/^(?!\|)[=\-_~|]{4,}\s*$/gm, "");

  // Strip document title + underline pattern: "Title Text\n========"
  text = text.replace(/^.{3,80}\n[=\-_~]{4,}\s*$/gm, "");

  // Strip inline separator runs that survived (e.g. "text ===== more text")
  text = text.replace(/\s*[=_~]{4,}\s*/g, " ");

  // "**: - item" or "**:\n- item" — ensure list items start on their own line
  text = text.replace(/\*\*:\s*-\s+/g, "**:\n\n- ");

  // Multiple inline bullets on one line: "…sentence. - Next bullet"
  text = text.replace(/([.!?])\s+-\s+(?=\*\*|[A-Z])/g, "$1\n\n- ");

  // Section headers stuck to bullets: "Report**: - The"
  text = text.replace(/(\*\*[^*\n]+?\*\*:)\s+-\s+/g, "$1\n\n- ");

  // Horizontal rules written as "---" without newlines
  text = text.replace(/([^\n])\s*---\s*/g, "$1\n\n---\n\n");

  // Collapse 3+ blank lines
  text = text.replace(/\n{3,}/g, "\n\n");

  text = formatPipeDelimitedTables(text);

  return text.trim();
}

type MarkdownContentProps = {
  content: string;
  variant?: "assistant" | "user";
  isStreaming?: boolean;
};

const assistantComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-4 border-b border-white/10 pb-2 text-lg font-semibold tracking-tight text-white first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2.5 mt-4 text-base font-semibold text-white first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-3 text-sm font-semibold text-[#10a37f] first:mt-0">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-3 leading-relaxed text-[#e8e8f0] last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-[#d4d4dc]">{children}</em>,
  ul: ({ children }) => (
    <ul className="mb-3 ml-1 list-none space-y-2 pl-0 last:mb-0 [&>li]:relative [&>li]:pl-5 [&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-[0.55em] [&>li]:before:h-1.5 [&>li]:before:w-1.5 [&>li]:before:rounded-full [&>li]:before:bg-[#10a37f] [&>li]:before:content-['']">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-2 pl-5 marker:text-[#10a37f] last:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed text-[#e8e8f0]">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-[#10a37f]/60 bg-white/[0.03] py-1 pl-4 italic text-[#c8c8d4]">
      {children}
    </blockquote>
  ),
  code: ({ className, children }) => {
    const isBlock = Boolean(className);
    if (isBlock) {
      return (
        <code className={`block overflow-x-auto rounded-lg bg-[#171717] px-3 py-2 font-mono text-xs text-[#a5f3d0] ${className ?? ""}`}>
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-[#171717] px-1.5 py-0.5 font-mono text-xs text-[#a5f3d0]">{children}</code>
    );
  },
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-xl border border-[#404040] bg-[#171717] p-3 last:mb-0">
      {children}
    </pre>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-[#10a37f] underline decoration-[#10a37f]/40 underline-offset-2 transition-colors hover:text-[#14c997] hover:decoration-[#14c997]"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-4 border-0 border-t border-white/10" />,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-[#404040]">
      <table className="w-full min-w-[280px] text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-[#1a1a1a] text-xs uppercase tracking-wide text-[#9ca3af]">{children}</thead>,
  th: ({ children }) => <th className="px-3 py-2 font-medium">{children}</th>,
  td: ({ children }) => <td className="border-t border-[#333] px-3 py-2 text-[#e8e8f0]">{children}</td>,
};

const userComponents: Components = {
  ...assistantComponents,
  p: ({ children }) => <p className="mb-2 leading-relaxed last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => (
    <ul className="mb-2 ml-1 list-none space-y-1 pl-0 last:mb-0 [&>li]:relative [&>li]:pl-4 [&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-[0.6em] [&>li]:before:h-1 [&>li]:before:w-1 [&>li]:before:rounded-full [&>li]:before:bg-white/80 [&>li]:before:content-['']">
      {children}
    </ul>
  ),
};

export function MarkdownContent({ content, variant = "assistant", isStreaming }: MarkdownContentProps) {
  const normalized = normalizeMarkdown(content);
  const components = variant === "user" ? userComponents : assistantComponents;

  return (
    <div className="markdown-body text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {normalized}
      </ReactMarkdown>
      {isStreaming && (
        <span
          className="ml-0.5 inline-block h-[1.1em] w-[2px] animate-pulse rounded-full bg-[#10a37f] align-text-bottom"
          aria-hidden
        />
      )}
    </div>
  );
}
