// REST client. All HTTP access to the backend lives here (coding-style §9:
// components never fetch directly). Same-origin in dev via the Vite proxy;
// VITE_API_BASE can point elsewhere for a separate deploy.

import type {
  HealthResponse,
  OnboardingRequest,
  OnboardingStatus,
  Routine,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";
const REQUEST_TIMEOUT_MS = 8000;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
      signal: controller.signal,
    });
  } catch (err) {
    // User-facing messages are Korean. Distinguish a timeout from a dead backend.
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.");
    }
    throw new ApiError(0, "서버에 연결할 수 없습니다.");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new ApiError(res.status, detail || `요청에 실패했습니다 (${res.status}).`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function getOnboarding(): Promise<OnboardingStatus> {
  return request<OnboardingStatus>("/onboarding");
}

export function submitOnboarding(body: OnboardingRequest): Promise<unknown> {
  return request<unknown>("/onboarding", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listRoutines(): Promise<Routine[]> {
  return request<Routine[]>("/routines");
}
