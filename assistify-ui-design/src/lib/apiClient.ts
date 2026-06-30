import { fullAppPath, isGuestReactPath } from "./routes";

export type ApiClientOptions = RequestInit;

export class ApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
  }
}

/** Accepts a bare array OR an object that wraps the array under `key`. */
export function unwrapList<T>(data: unknown, key: string): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === "object") {
    const v = (data as Record<string, unknown>)[key];
    if (Array.isArray(v)) return v as T[];
  }
  return [];
}

export function getCSRFToken(): string | null {
  if (typeof document === "undefined") return null;

  const name = "csrf_token=";
  const decodedCookie = decodeURIComponent(document.cookie ?? "");
  for (let cookie of decodedCookie.split(";")) {
    cookie = cookie.trim();
    if (cookie.indexOf(name) === 0) {
      return cookie.substring(name.length);
    }
  }

  const metaTag = document.querySelector('meta[name="csrf-token"]');
  return metaTag?.getAttribute("content") ?? null;
}

async function parseApiError(response: Response): Promise<string> {
  try {
    const data = (await response.clone().json()) as {
      detail?: string | Array<{ msg?: string }>;
      message?: string;
    };
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((item) => item?.msg || String(item)).join("; ");
    }
    if (data?.message) return String(data.message);
  } catch {
    // fall through
  }
  return response.statusText || `Request failed (${response.status})`;
}

function validateUrl(url: string): void {
  if (typeof window === "undefined") return;
  if (!url.startsWith("/") && !url.startsWith(window.location.origin)) {
    throw new Error("Invalid URL");
  }
}

function applySecurityDefaults(url: string, options: ApiClientOptions = {}): RequestInit {
  validateUrl(url);
  const headers = new Headers(options.headers ?? {});
  const csrfToken = getCSRFToken();
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return { ...options, headers, credentials: options.credentials ?? "same-origin" };
}

export async function secureFetch(url: string, options: ApiClientOptions = {}): Promise<Response> {
  const response = await fetch(url, applySecurityDefaults(url, options));
  if (response.status === 401) {
    if (typeof window !== "undefined" && !isGuestReactPath(window.location.pathname)) {
      window.location.href = fullAppPath("/login");
    }
    throw new ApiClientError("Authentication error", response.status);
  }
  return response;
}

async function request<TResponse = unknown>(url: string, options: ApiClientOptions = {}): Promise<TResponse> {
  const response = await secureFetch(url, options);
  if (!response.ok) {
    throw new ApiClientError(await parseApiError(response), response.status);
  }
  if (response.status === 204) return undefined as TResponse;
  return (await response.json()) as TResponse;
}

function withJsonBody(body: unknown, options: ApiClientOptions = {}): ApiClientOptions {
  const headers = new Headers(options.headers ?? {});
  let resolvedBody: BodyInit | null | undefined;
  if (body instanceof FormData || body instanceof URLSearchParams || body instanceof Blob) {
    resolvedBody = body;
  } else if (body === undefined || body === null) {
    resolvedBody = undefined;
  } else {
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    resolvedBody = JSON.stringify(body);
  }
  return { ...options, headers, body: resolvedBody };
}

export const apiClient = {
  get: <TResponse = unknown>(url: string, options: ApiClientOptions = {}) =>
    request<TResponse>(url, { ...options, method: "GET" }),
  post: <TResponse = unknown>(url: string, body?: unknown, options: ApiClientOptions = {}) =>
    request<TResponse>(url, { ...withJsonBody(body, options), method: "POST" }),
  put: <TResponse = unknown>(url: string, body?: unknown, options: ApiClientOptions = {}) =>
    request<TResponse>(url, { ...withJsonBody(body, options), method: "PUT" }),
  patch: <TResponse = unknown>(url: string, body?: unknown, options: ApiClientOptions = {}) =>
    request<TResponse>(url, { ...withJsonBody(body, options), method: "PATCH" }),
  delete: <TResponse = unknown>(url: string, body?: unknown, options: ApiClientOptions = {}) =>
    request<TResponse>(url, { ...withJsonBody(body, options), method: "DELETE" }),
};
