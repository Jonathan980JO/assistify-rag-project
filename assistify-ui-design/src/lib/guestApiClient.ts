import { getCSRFToken } from "./apiClient";

export class GuestApiClientError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "GuestApiClientError";
    this.status = status;
  }
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

function applySecurityDefaults(url: string, options: RequestInit = {}): RequestInit {
  const headers = new Headers(options.headers ?? {});
  const csrfToken = getCSRFToken();
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return { ...options, headers, credentials: options.credentials ?? "same-origin" };
}

async function request<TResponse = unknown>(url: string, options: RequestInit = {}): Promise<TResponse> {
  const response = await fetch(url, applySecurityDefaults(url, options));
  if (!response.ok) {
    throw new GuestApiClientError(await parseApiError(response), response.status);
  }
  if (response.status === 204) return undefined as TResponse;
  return (await response.json()) as TResponse;
}

function withJsonBody(body: unknown, options: RequestInit = {}): RequestInit {
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

export const guestApiClient = {
  get: <TResponse = unknown>(url: string, options: RequestInit = {}) =>
    request<TResponse>(url, { ...options, method: "GET" }),
  post: <TResponse = unknown>(url: string, body?: unknown, options: RequestInit = {}) =>
    request<TResponse>(url, { ...withJsonBody(body, options), method: "POST" }),
  patch: <TResponse = unknown>(url: string, body?: unknown, options: RequestInit = {}) =>
    request<TResponse>(url, { ...withJsonBody(body, options), method: "PATCH" }),
  delete: <TResponse = unknown>(url: string, options: RequestInit = {}) =>
    request<TResponse>(url, { ...options, method: "DELETE" }),
};
