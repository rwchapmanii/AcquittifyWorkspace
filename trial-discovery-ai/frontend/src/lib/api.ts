const configuredApiBase =
  process.env.NEXT_PUBLIC_PEREGRINE_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL;
const configuredLooksLocal =
  !!configuredApiBase &&
  (configuredApiBase.includes("localhost") ||
    configuredApiBase.includes("127.0.0.1"));
const shouldUseConfiguredApiBase =
  !!configuredApiBase &&
  !(process.env.NODE_ENV === "production" && configuredLooksLocal);

export const API_BASE =
  (shouldUseConfiguredApiBase ? configuredApiBase : null) ||
  (process.env.NODE_ENV === "development"
    ? "http://localhost:8002"
    : "https://api.acquittify.ai");
const CSRF_COOKIE_NAME =
  process.env.NEXT_PUBLIC_PEREGRINE_CSRF_COOKIE_NAME || "peregrine_csrf";
const CSRF_HEADER_NAME =
  process.env.NEXT_PUBLIC_PEREGRINE_CSRF_HEADER_NAME || "X-CSRF-Token";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const encodedName = encodeURIComponent(name);
  const parts = document.cookie.split("; ");
  for (const part of parts) {
    if (part.startsWith(`${encodedName}=`)) {
      return decodeURIComponent(part.slice(encodedName.length + 1));
    }
  }
  return null;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers ?? undefined);
  const method = (init.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken && !headers.has(CSRF_HEADER_NAME)) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
  }
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
}
