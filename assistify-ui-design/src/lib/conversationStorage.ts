const USER_KEY = "assistify_active_conversation_id";
const GUEST_KEY = "assistify_guest_active_conversation_id";

function keyFor(scope: "user" | "guest") {
  return scope === "guest" ? GUEST_KEY : USER_KEY;
}

export function getLastActiveConversationId(scope: "user" | "guest"): string | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(keyFor(scope));
  return raw && raw.trim() ? raw.trim() : null;
}

export function setLastActiveConversationId(scope: "user" | "guest", id: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(keyFor(scope), id);
}

export function clearLastActiveConversationId(scope: "user" | "guest") {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(keyFor(scope));
}
