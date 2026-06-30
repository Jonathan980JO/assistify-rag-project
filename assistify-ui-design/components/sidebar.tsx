"use client";

import { Check, Edit2, MessageSquare, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { LogoutLink } from "@/src/components/ui/LogoutLink";

interface SidebarProps {
  conversations: { id: string; title: string; updated_at: string }[];
  activeConversationId: string | null;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onRenameConversation: (id: string, title: string) => void | Promise<void>;
  onDeleteConversation: (id: string) => void;
  onClearAll: () => void;
}

export function Sidebar({
  conversations,
  activeConversationId,
  onNewChat,
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
  onClearAll,
}: SidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const startRename = (id: string, title: string) => {
    setEditingId(id);
    setEditTitle(title || "");
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditTitle("");
  };

  const commitRename = async (id: string) => {
    const title = editTitle.trim();
    if (!title) {
      cancelRename();
      return;
    }
    await onRenameConversation(id, title.slice(0, 80));
    cancelRename();
  };

  return (
    <aside className="flex h-full w-64 flex-col border-r border-[#333333] bg-[#171717]">
      <div className="border-b border-[#333333] p-4">
        <Button
          type="button"
          className="h-10 w-full gap-2 bg-[#10a37f] text-sm font-medium text-white hover:bg-[#0d8a6b]"
          onClick={onNewChat}
        >
          <Plus size={20} />
          New Chat
        </Button>
        <button
          type="button"
          className="mt-2 w-full rounded-lg border border-[#444444] py-1.5 text-xs text-[#9ca3af] hover:bg-[#2b2b2b] hover:text-[#fafaff]"
          onClick={onClearAll}
        >
          Clear all
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {conversations.map((c) => (
          <div
            key={c.id}
            className="relative mb-1"
            onMouseEnter={() => setHoveredId(c.id)}
            onMouseLeave={() => setHoveredId(null)}
          >
            {editingId === c.id ? (
              <div className="flex items-center gap-1 rounded-lg bg-[#2b2b2b] p-2">
                <input
                  className="min-w-0 flex-1 rounded border border-[#444] bg-[#232323] px-2 py-1 text-xs text-[#fafaff]"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void commitRename(c.id);
                    if (e.key === "Escape") cancelRename();
                  }}
                  autoFocus
                />
                <button type="button" onClick={() => commitRename(c.id)} className="p-1 text-[#10a37f]" aria-label="Save rename">
                  <Check size={14} />
                </button>
                <button type="button" onClick={cancelRename} className="p-1 text-[#9ca3af]" aria-label="Cancel rename">
                  <X size={14} />
                </button>
              </div>
            ) : (
              <button
                type="button"
                className={`w-full rounded-lg p-3 text-left text-sm transition-colors ${
                  activeConversationId === c.id
                    ? "bg-[#10a37f] text-white"
                    : "text-[#fafaff] hover:bg-[#2b2b2b]"
                }`}
                onClick={() => onSelectConversation(c.id)}
              >
                <div className="flex items-center gap-2">
                  <MessageSquare size={16} />
                  <span className="truncate">{c.title || "Untitled"}</span>
                </div>
              </button>
            )}
            {hoveredId === c.id && editingId !== c.id && (
              <div className="absolute top-1/2 right-2 flex -translate-y-1/2 gap-1">
                <button
                  type="button"
                  className="rounded p-1.5 text-[#9ca3af] transition-colors hover:bg-[#333333] hover:text-[#fafaff]"
                  onClick={() => startRename(c.id, c.title)}
                  aria-label="Rename chat"
                >
                  <Edit2 size={14} />
                </button>
                <button
                  type="button"
                  className="rounded p-1.5 text-[#9ca3af] transition-colors hover:bg-[#333333] hover:text-[#fafaff]"
                  onClick={() => onDeleteConversation(c.id)}
                  aria-label="Delete chat"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-[#333333] p-4">
        <LogoutLink />
      </div>
    </aside>
  );
}
