// REST client. All HTTP access to the backend lives here (coding-style §9:
// components never fetch directly). Same-origin in dev via the Vite proxy;
// VITE_API_BASE can point elsewhere for a separate deploy.

import { restBase } from "./origin";
import type {
  CheckinResult,
  ConditionCheckin,
  HealthResponse,
  OnboardingRequest,
  OnboardingStatus,
  Routine,
} from "./types";

const BASE = restBase();
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

// ADR-030 (b): app-open prewarm. Called when the Tauri app opens/focuses (user
// intent) so models start loading before 세션 시작, cutting cold start. Best-effort
// — failures are swallowed by the caller; 세션 시작 retries and surfaces VRAM 안내.
export function prewarmModels(): Promise<{ status: string }> {
  return request<{ status: string }>("/prewarm", { method: "POST" });
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

// 세션 전 자가보고 컨디션 체크인 (ADR-023). session_id 없이 저장되고, 세션 생성 시
// 백엔드가 연결한다. 선택형이라 실패해도 호출부는 세션을 계속 시작한다.
export function submitCheckin(body: ConditionCheckin): Promise<CheckinResult> {
  return request<CheckinResult>("/api/condition/checkin", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── 능동 알림 스케줄 (ADR-027) ──────────────────────────────────────────────
// 경량 경로 — 모델 없이 일정만 읽는다(ADR-030). 폴러(useReminders)가 /due 를 주기적으로
// 호출해 native toast 를 띄우고, /pending 으로 앱 내 배지·앱-오픈 라우팅을 구동한다.

export interface Reminder {
  key: string;
  kind: "workout" | "checkin";
  title: string;
  body: string;
  scheduled_for: string;
}

export interface NotificationSettings {
  enabled: boolean;
  lead_minutes: number;
  workout_time: string;
  mute_start: string | null;
  mute_end: string | null;
  checkin_enabled: boolean;
  checkin_time: string;
  poll_interval_sec: number; // 읽기 전용 (config)
  catchup_minutes: number; // 읽기 전용 (config)
}

/** 지금 toast 로 띄울 리마인드(폴링마다 호출). 반환분은 서버가 발생 처리해 중복 방지. */
export function getDueReminders(): Promise<Reminder[]> {
  return request<Reminder[]>("/schedule/due");
}

/** 앱 내 배지/리스트 + 앱-오픈 라우팅용 — 오늘 발생했고 아직 처리 안 한 리마인드. */
export function getPendingReminders(): Promise<Reminder[]> {
  return request<Reminder[]>("/schedule/pending");
}

/** 리마인드 처리됨 표시(세션 시작/닫음). key 생략 시 현재 pending 전부 ack. */
export function ackReminder(key?: string): Promise<{ acked: string[] }> {
  return request<{ acked: string[] }>("/schedule/ack", {
    method: "POST",
    body: JSON.stringify({ key: key ?? null }),
  });
}

export function getNotificationSettings(): Promise<NotificationSettings> {
  return request<NotificationSettings>("/schedule/settings");
}

export function updateNotificationSettings(
  patch: Partial<Omit<NotificationSettings, "poll_interval_sec" | "catchup_minutes">>,
): Promise<NotificationSettings> {
  return request<NotificationSettings>("/schedule/settings", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}
