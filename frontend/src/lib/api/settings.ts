/**
 * 系统设置 API：用户资料、全局设置与设备保活。
 */
import { MEDIUM_TIMEOUT_MS, request, requestBlob } from "./core";

// ─── 用户设置 ───

export const changePassword = (token: string, oldPassword: string, newPassword: string) =>
  request<{ success: boolean; message: string }>("/user/password", {
    method: "PUT",
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  }, token);

export const getTOTPStatus = (token: string) =>
  request<{ enabled: boolean; secret?: string }>("/user/totp/status", {}, token);

export const setupTOTP = (token: string) =>
  request<{ enabled: boolean; secret: string }>("/user/totp/setup", {
    method: "POST",
  }, token);

export const fetchTOTPQRCode = async (token: string) => {
  const blob = await requestBlob("/user/totp/qrcode", {}, token);
  return window.URL.createObjectURL(blob);
};

export const enableTOTP = (token: string, totpCode: string) =>
  request<{ success: boolean; message: string }>("/user/totp/enable", {
    method: "POST",
    body: JSON.stringify({ totp_code: totpCode }),
  }, token);

export const disableTOTP = (token: string, totpCode: string) =>
  request<{ success: boolean; message: string }>("/user/totp/disable", {
    method: "POST",
    body: JSON.stringify({ totp_code: totpCode }),
  }, token);

export interface ChangeUsernameResponse {
  success: boolean;
  message: string;
  access_token?: string;
}

export const changeUsername = (token: string, newUsername: string, password: string) =>
  request<ChangeUsernameResponse>("/user/username", {
    method: "PUT",
    body: JSON.stringify({ new_username: newUsername, password: password }),
  }, token);

// ─── 全局设置 ───

export interface GlobalSettings {
  chat_center_enabled?: boolean;
  log_retention_days?: number;    // 日志保留天数，默认 7
  data_dir?: string | null;
  global_proxy?: string | null;
  tg_global_concurrency?: number | null;
  device_keepalive_enabled?: boolean;
  device_keepalive_interval_days?: number;
  telegram_bot_notify_enabled?: boolean;
  telegram_bot_login_notify_enabled?: boolean;
  telegram_bot_code_enabled?: boolean;
  telegram_bot_code_status?: string;
  telegram_bot_quiet_hours_enabled?: boolean;
  telegram_bot_quiet_hours_start?: string | null;
  telegram_bot_quiet_hours_end?: string | null;
  /** GET 不回传明文；写入时仅非空时更新 */
  telegram_bot_token?: string | null;
  telegram_bot_token_set?: boolean;
  telegram_bot_chat_id?: string | null;
  telegram_bot_message_thread_id?: number | null;
  timezone?: string;
  auto_backup_enabled?: boolean;
  auto_backup_interval_hours?: number | null;
  auto_backup_keep?: number | null;
  webdav_url?: string | null;
  webdav_username?: string | null;
  /** GET 永不返回明文；写入时仅在非空时更新 */
  webdav_password?: string | null;
  /** 服务端是否已保存 WebDAV 密码 */
  webdav_password_set?: boolean;
  webdav_remote_dir?: string | null;
}

export const getGlobalSettings = (token: string) =>
  request<GlobalSettings>("/config/settings", {}, token);

export const saveGlobalSettings = async (token: string, settings: GlobalSettings) => {
  const result = await request<{ success: boolean; message: string }>("/config/settings", {
    method: "POST",
    body: JSON.stringify(settings),
  }, token);
  if (result.success && typeof settings.chat_center_enabled === 'boolean') {
    window.dispatchEvent(new CustomEvent('chat-center-changed', { detail: settings.chat_center_enabled }));
  }
  return result;
};

export const testBotNotification = (token: string, message?: string) =>
  request<{ success: boolean; message: string }>("/config/bot/test", {
    method: "POST",
    body: JSON.stringify({ message: message || undefined }),
  }, token);

export interface DeviceKeepaliveRunResult {
  success: boolean;
  enabled: boolean;
  checked: number;
  kept_alive: number;
  skipped: number;
  failed: number;
  interval_days?: number | null;
  results: Array<{ account_name: string; status: string; message?: string }>;
}

export const runDeviceKeepalive = (token: string) =>
  request<DeviceKeepaliveRunResult>(
    "/config/settings/device-keepalive/run",
    { method: "POST" },
    token,
    // 多账号保活可能超过默认 30s
    MEDIUM_TIMEOUT_MS,
  );
