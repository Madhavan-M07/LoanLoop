// Server-only API client, typed by the generated OpenAPI schema. Runs inside Next.js (server
// components and server actions), so the bearer token stays in an httpOnly cookie and never
// reaches browser JavaScript.
import "server-only";

import createClient from "openapi-fetch";

import type { paths } from "./schema";

const API_URL = process.env.LOANLOOP_API_URL ?? "http://127.0.0.1:8000";
const TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function apiFor(token: string) {
  return createClient<paths>({
    baseUrl: API_URL,
    headers: { Authorization: `Bearer ${token}` },
    fetch: (req: Request) => fetch(req, { cache: "no-store", signal: AbortSignal.timeout(TIMEOUT_MS) }),
  });
}

function detailOf(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const d = (error as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    return "The request was not valid.";
  }
  return "";
}

/**
 * Unwraps an openapi-fetch call: returns the data, or throws ApiError with a short message.
 * Network failures (backend down, timeout) become status 0.
 */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await call;
  } catch {
    throw new ApiError(0, "Can't reach the LoanLoop API. Is the backend running on port 8000?");
  }
  const { data, error, response } = result;
  if (error !== undefined || data === undefined) {
    const status = response.status;
    let message = detailOf(error);
    if (!message && status === 401) message = "Your session is no longer valid. Sign in again.";
    if (!message && status >= 500) message = "The API had a problem. Check the backend logs.";
    throw new ApiError(status, message || `Request failed (${status}).`);
  }
  return data;
}

export function describeError(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Something went wrong. Check that the backend is running.";
}
