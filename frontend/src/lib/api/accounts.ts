/**
 * 账号管理 API：登录流程、CRUD、状态检测、设备、官方消息、账号日志。
 */
import { LONG_TIMEOUT_MS, MEDIUM_TIMEOUT_MS, fetchWithAuth, request, requestBlob } from "./core";

export interface LoginStartRequest {
  account_name: string;
  phone_number: string;
  api_id?: number;
  api_hash?: string;
}

export interface LoginStartResponse {
  phone_code_hash: string;
  phone_number: string;
  account_name: string;
  message: string;
  delivery_type?: string | null;
  next_type?: string | null;
  retry_after?: number | null;
}

export interface LoginVerifyRequest {
  account_name: string;
  phone_number: string;
  phone_code: string;
  phone_code_hash: string;
  password?: string;
}

export interface LoginVerifyResponse {
  success: boolean;
  user_id?: number;
  first_name?: string;
  username?: string;
  message: string;
}

export interface QrLoginStartRequest {
  account_name: string;
  api_id?: number;
  api_hash?: string;
}

export interface QrLoginStartResponse {
  login_id: string;
  qr_uri: string;
  qr_image?: string | null;
  expires_at: string;
}

export interface QrLoginStatusResponse {
  status: string;
  expires_at?: string;
  message?: string;
  account?: AccountInfo | null;
  user_id?: number;
  first_name?: string;
  username?: string;
}

export interface QrLoginCancelResponse {
  success: boolean;
  message: string;
}

export interface QrLoginPasswordRequest {
  login_id: string;
  password: string;
}

export interface QrLoginPasswordResponse {
  success: boolean;
  message: string;
  account?: AccountInfo | null;
  user_id?: number;
  first_name?: string;
  username?: string;
}

export interface AccountInfo {
  name: string;
  session_file: string;
  exists: boolean;
  size: number;
  remark?: string | null;
  route_mode?: 'primary' | 'fallback' | 'direct' | 'setup_required' | null;
  route_status?: string | null;
  node_label?: string | null;
  latency_ms?: number | null;
  route_checked_at?: string | null;
  exit_ip?: string | null;
  exit_country?: string | null;
  exit_region?: string | null;
  exit_checked_at?: string | null;
  exit_lookup_status?: 'pending' | 'verified' | 'failed';
  shared_node?: boolean;
  status?: "connected" | "invalid" | "checking" | "error" | string;
  status_message?: string | null;
  status_code?: string | null;
  status_checked_at?: string | null;
  needs_relogin?: boolean;
  tags?: string[];
}

export interface AccountStatusCheckRequest {
  account_names?: string[];
  timeout_seconds?: number;
  refresh_avatar?: boolean;
  inspect_resources?: boolean;
  reconcile_orphans?: boolean;
}

export interface AccountStatusItem {
  account_name: string;
  ok: boolean;
  status: "connected" | "invalid" | "error" | "not_found" | string;
  message?: string;
  code?: string;
  checked_at?: string;
  needs_relogin?: boolean;
  user_id?: number;
  avatar_refreshed?: boolean;
  avatar_refresh_error?: boolean;
  route_mode?: AccountInfo['route_mode'];
  route_status?: string | null;
  node_label?: string | null;
  latency_ms?: number | null;
  route_checked_at?: string | null;
  exit_ip?: string | null;
  exit_country?: string | null;
  exit_region?: string | null;
  exit_checked_at?: string | null;
  exit_lookup_status?: AccountInfo['exit_lookup_status'];
  shared_node?: boolean;
  telebox?: { account: string; status: string; enabled: boolean; authorized: boolean; message?: string } | null;
}

export interface AccountStatusCheckResponse {
  results: AccountStatusItem[];
}

export interface AccountDeviceInfo {
  hash: string;
  current: boolean;
  official_app: boolean;
  password_pending: boolean;
  device_model: string;
  platform: string;
  system_version: string;
  app_name: string;
  app_version: string;
  date_created?: string | null;
  date_active?: string | null;
  ip: string;
  country: string;
  region: string;
}

export interface OfficialMessageInfo {
  id?: number | null;
  date?: string | null;
  text: string;
  outgoing: boolean;
}

export interface LoginBackupImportResult {
  restored: number;
  skipped: number;
}

/** Only authorized account sessions and the API credentials needed to reuse them. */
export const exportAccountLoginBackup = (token: string, password: string, allowForceStopContainer: boolean, allowRestoreServer: boolean) =>
  requestBlob("/accounts/login-backup/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, allow_force_stop_container: allowForceStopContainer, allow_restore_server: allowRestoreServer }),
  }, token, LONG_TIMEOUT_MS);

/** Let the browser set multipart/form-data's boundary. */
export async function importAccountLoginBackup(
  token: string,
  file: File,
  password: string,
): Promise<LoginBackupImportResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("password", password);
  const response = await fetchWithAuth(
    "/accounts/login-backup/import",
    {},
    { method: "POST", body: form },
    token,
    LONG_TIMEOUT_MS,
  );
  return response.json() as Promise<LoginBackupImportResult>;
}

export const startAccountLogin = (token: string, data: LoginStartRequest) =>
  request<LoginStartResponse>("/accounts/login/start", {
    method: "POST",
    body: JSON.stringify(data),
  }, token, 65_000);

export const resendAccountLogin = (token: string, data: Pick<LoginVerifyRequest, 'account_name' | 'phone_number' | 'phone_code_hash'>) =>
  request<LoginStartResponse>("/accounts/login/resend", {
    method: "POST", body: JSON.stringify(data),
  }, token, 35_000);

export const cancelAccountLogin = (token: string, data: Pick<LoginVerifyRequest, 'account_name' | 'phone_number' | 'phone_code_hash'>) =>
  request<{ canceled: boolean }>("/accounts/login/cancel", {
    method: "POST", body: JSON.stringify(data),
  }, token);

export const verifyAccountLogin = (token: string, data: LoginVerifyRequest) =>
  request<LoginVerifyResponse>("/accounts/login/verify", {
    method: "POST",
    body: JSON.stringify(data),
  }, token);

export const listAccounts = (token: string) =>
  request<{ accounts: AccountInfo[]; total: number }>("/accounts", {}, token);

export const checkAccountsStatus = (token: string, data: AccountStatusCheckRequest) =>
  request<AccountStatusCheckResponse>(
    "/accounts/status/check",
    { method: "POST", body: JSON.stringify(data) },
    token,
    MEDIUM_TIMEOUT_MS,
  );

/** 异步批量状态检测 Job */
export interface AccountStatusJob {
  job_id: string;
  kind: string;
  status: "running" | "canceling" | "canceled" | "completed" | "failed" | string;
  created_at?: string;
  updated_at?: string;
  finished_at?: string | null;
  progress?: { total?: number; done?: number; ok?: number; fail?: number };
  summary?: { total?: number; checked?: number; ok?: number; fail?: number };
  results?: AccountStatusItem[];
  logs?: Array<{ time?: string; level?: string; message?: string; ref?: string | null }>;
  error?: string | null;
  payload?: { account_names?: string[]; timeout_seconds?: number };
}

export const startAccountStatusCheckJob = (
  token: string,
  data: AccountStatusCheckRequest,
) =>
  request<AccountStatusJob>("/accounts/status/check-jobs", {
    method: "POST",
    body: JSON.stringify(data),
  }, token);

export const getAccountStatusCheckJob = (token: string, jobId: string) =>
  request<AccountStatusJob>(
    `/accounts/status/check-jobs/${encodeURIComponent(jobId)}`,
    {},
    token,
  );

export const listAccountStatusCheckJobs = (token: string, limit = 10) =>
  request<{ jobs: AccountStatusJob[] }>(
    `/accounts/status/check-jobs?limit=${encodeURIComponent(String(limit))}`,
    {},
    token,
  );

export const cancelAccountStatusCheckJob = (token: string, jobId: string) =>
  request<{ ok: boolean; job_id: string }>(
    `/accounts/status/check-jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
    token,
  );

export const deleteAccount = (token: string, accountName: string) =>
  request<{ success: boolean; message: string }>(`/accounts/${accountName}`, {
    method: "DELETE",
  }, token);

export const listAccountDevices = (token: string, accountName: string) =>
  request<{ devices: AccountDeviceInfo[]; total: number }>(
    `/accounts/${encodeURIComponent(accountName)}/devices`,
    {},
    token,
    MEDIUM_TIMEOUT_MS,
  );

export const terminateAccountDevice = (token: string, accountName: string, authHash: string) =>
  request<{ success: boolean; message: string }>(`/accounts/${encodeURIComponent(accountName)}/devices/${encodeURIComponent(authHash)}`, {
    method: "DELETE",
  }, token);

export const listAccountOfficialMessages = (token: string, accountName: string, limit = 20) =>
  request<{ messages: OfficialMessageInfo[]; total: number }>(
    `/accounts/${encodeURIComponent(accountName)}/official-messages?limit=${encodeURIComponent(String(limit))}`,
    {},
    token,
    MEDIUM_TIMEOUT_MS,
  );

export const updateAccount = (
  token: string,
  accountName: string,
  data: {
    new_account_name?: string | null;
    remark?: string | null;
    tags?: string[];
  }
) =>
  request<{ success: boolean; message: string; account?: AccountInfo | null }>(`/accounts/${accountName}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  }, token);

export const startQrLogin = (token: string, data: QrLoginStartRequest) =>
  request<QrLoginStartResponse>("/accounts/qr/start", {
    method: "POST",
    body: JSON.stringify(data),
  }, token, 65_000);

export const getQrLoginStatus = (token: string, loginId: string) =>
  request<QrLoginStatusResponse>(`/accounts/qr/status?login_id=${encodeURIComponent(loginId)}`, {}, token);

export const cancelQrLogin = (token: string, loginId: string) =>
  request<QrLoginCancelResponse>("/accounts/qr/cancel", {
    method: "POST",
    body: JSON.stringify({ login_id: loginId }),
  }, token);

export const submitQrPassword = (token: string, data: QrLoginPasswordRequest) =>
  request<QrLoginPasswordResponse>("/accounts/qr/password", {
    method: "POST",
    body: JSON.stringify(data),
  }, token);

/**
 * 下载账号头像。复用 requestBlob 的鉴权与 401 跳转；失败时抛 ApiError，
 * 调用方按需 catch 回退到默认头像。
 */
export const fetchAccountAvatar = (token: string, accountName: string) =>
  requestBlob(`/accounts/${encodeURIComponent(accountName)}/avatar`, { cache: 'no-store' }, token);
