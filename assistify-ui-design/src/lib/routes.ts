/** Path helpers — Next.js `basePath` is `/frontend`; form POSTs use root paths on :7001. */

export const FRONTEND_BASE = "/frontend";

/** For Next.js `Link` / `useRouter` (basePath is applied automatically). */
export function appPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (normalized === "/") return "/";
  const trimmed = normalized.replace(/\/+$/, "");
  return `${trimmed}/`;
}

/** Full browser URL path including basePath (for window.location, plain <a href>). */
export function fullAppPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (normalized === "/") return `${FRONTEND_BASE}/`;
  const trimmed = normalized.replace(/\/+$/, "");
  return `${FRONTEND_BASE}${trimmed}/`;
}

/** @deprecated Use appPath for Link, fullAppPath for window.location */
export function reactPath(path: string): string {
  return fullAppPath(path);
}

/** Root-relative path for form actions and OAuth (not under basePath). */
export function rootPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return normalized.replace(/\/+$/, "") || "/";
}

export const AUTH_PUBLIC_PATHS = [
  "/login",
  "/register",
  "/verify-otp",
  "/forgot-password",
  "/reset-password",
  "/change-username",
  "/guest",
] as const;

export function isGuestReactPath(path: string): boolean {
  const stripped = path.replace(/^\/frontend\/?/, "/").replace(/\/+$/, "") || "/";
  return stripped === "/guest" || stripped.startsWith("/guest/");
}

export function isAuthPublicReactPath(path: string): boolean {
  const stripped = path.replace(/^\/frontend\/?/, "/").replace(/\/+$/, "") || "/";
  return AUTH_PUBLIC_PATHS.some((p) => stripped === p || stripped.startsWith(`${p}/`));
}
