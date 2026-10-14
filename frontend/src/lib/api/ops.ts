/**
 * 运维 Ops API：调度预览、内存统计、版本检查、运行时状态。
 */
import { request } from "./core";
export interface ScheduledJob {
  id: string;
  name: string;
  next_run_time?: string | null;
  trigger: string;
  kind: "sign" | "legacy_db" | "system" | "other" | string;
  execution_mode?: string | null;
  range_start?: string | null;
  range_end?: string | null;
  task_name?: string | null;
  account_name?: string | null;
}

export interface ScheduledJobsResponse {
  jobs: ScheduledJob[];
  total: number;
  timezone: string;
}

export const listScheduledJobs = (token: string) =>
  request<ScheduledJobsResponse>("/ops/scheduled-jobs", {}, token);

export interface MemoryStatsResponse {
  available: boolean;
  stats: Record<string, unknown>;
}

export const getMemoryStats = (token: string) =>
  request<MemoryStatsResponse>("/ops/memory", {}, token);

export interface RuntimeStatus {
  ready: boolean;
  scheduler_lock_held: boolean;
  legacy_tasks_writable: boolean;
  /** 旧 /api/tasks 路由已移除 */
  legacy_tasks_removed?: boolean;
  database_is_sqlite: boolean;
  monitor_shard: string;
  monitor_allowlist: string;
  scheduler_role?: string;
  uptime_seconds?: number;
}

export const getRuntimeStatus = (token: string) =>
  request<RuntimeStatus>("/ops/runtime-status", {}, token);

export interface AppVersionInfo {
  version: string;
  git_sha: string;
  git_branch: string;
  build_time: string;
  app_name: string;
  os_platform?: string;
  python: string;
  update_check_enabled: boolean;
}

export interface UpdateCheckInfo {
  enabled: boolean;
  latest_version: string | null;
  latest_url: string | null;
  update_available: boolean;
  checked_at: string | null;
  error: string | null;
  source: string;
  cached: boolean;
}

export interface AppVersionCheckResult extends AppVersionInfo {
  update_check: UpdateCheckInfo;
}

export const getAppVersion = (token: string) =>
  request<AppVersionInfo>("/ops/version", {}, token);

export const checkAppVersion = (token: string, force = false) =>
  request<AppVersionCheckResult>(
    `/ops/version/check?force=${force ? "true" : "false"}`,
    { method: "POST" },
    token,
  );
