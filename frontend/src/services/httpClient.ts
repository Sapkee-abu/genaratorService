import type { ApiError } from "../types/api";

// Portal builds share environment definitions with Monitor's auth/API client.
// Keep the Generator prefix local so it cannot redirect central login requests.
const BASE_URL = import.meta.env.VITE_PORTAL === "true"
  ? "/api/generator"
  : import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8010";
const apiUrl = (path: string) => BASE_URL + (import.meta.env.VITE_PORTAL === "true" ? path.replace(/^\/api/, "") : path);

export class HttpError extends Error implements ApiError {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {credentials: "same-origin", ...init});
  } catch {
    throw new HttpError("ไม่สามารถเชื่อมต่อ Generator Service ได้");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (body?.detail?.message) message = body.detail.message;
    } catch {
      // response body wasn't JSON - keep the generic message
    }
    throw new HttpError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function putJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export interface BlobWithHeaders {
  blob: Blob;
  headers: Headers;
}

export async function getBlob(path: string): Promise<BlobWithHeaders> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {credentials: "same-origin"});
  } catch {
    throw new HttpError("ไม่สามารถเชื่อมต่อ Generator Service ได้");
  }
  if (!response.ok) throw new HttpError(`Request failed (${response.status})`, response.status);
  return { blob: await response.blob(), headers: response.headers };
}
