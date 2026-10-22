/**
 * 系统设置 API：用户资料、全局设置与设备保活。
 */
import { MEDIUM_TIMEOUT_MS, request, requestBlob } from "./core";

// ─── 用户设置 ───

export const changePassword = (token: string, oldPassword: string, newPassword: string) =>
  request<{ success: boolean; message: string; access_token: string }>("/user/password", {
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
  request<{ success: boolean; message: string; access_token: string }>("/user/totp/enable", {
    method: "POST",
    body: JSON.stringify({ totp_code: totpCode }),
  }, token);

export const disableTOTP = (token: string, totpCode: string) =>
  request<{ success: boolean; message: string; access_token: string }>("/user/totp/disable", {
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
  tg_global_concurrency?: number | null;
  device_keepalive_enabled?: boolean;
  device_keepalive_interval_days?: number;
  telegram_bot_notify_enabled?: boolean;
  telegram_bot_login_notify_enabled?: boolean;
  telegram_bot_code_enabled?: boolean;
  telegram_bot_code_status?: string;
  /** GET 不回传明文；写入时仅非空时更新 */
  telegram_bot_token?: string | null;
  telegram_bot_token_set?: boolean;
  telegram_bot_chat_id?: string | null;
  telegram_bot_message_thread_id?: number | null;
  telegram_bot_web_url?: string | null;
  timezone?: string;
  appearance_accent_color?: string;
  hero_position_x?: number;
  hero_position_y?: number;
}

export const getGlobalSettings = (token: string) =>
  request<GlobalSettings>("/config/settings", {}, token);

export const saveGlobalSettings = async (token: string, settings: GlobalSettings) => {
  const result = await request<{ success: boolean; message: string; telegram_web_menu_synced?: boolean | null }>("/config/settings", {
    method: "POST",
    body: JSON.stringify(settings),
  }, token);
  if (result.success && typeof settings.chat_center_enabled === 'boolean') {
    window.dispatchEvent(new CustomEvent('chat-center-changed', { detail: settings.chat_center_enabled }));
  }
  return result;
};

export interface SubscriptionSourceStatus {
  configured: boolean;
  status: string;
  last_refreshed_at: string | null;
  imported_count: number;
  usable_count: number;
  unsupported_count: number;
  label: string | null;
}

export interface ProxySubscriptionSettings {
  primary: SubscriptionSourceStatus;
  fallback: SubscriptionSourceStatus;
  latency_threshold_ms: number;
  route_mode: 'primary' | 'fallback' | 'direct' | 'setup_required' | string;
}

export interface ProxySubscriptionUpdate {
  primary_url?: string | null;
  fallback_url?: string | null;
  latency_threshold_ms?: number;
}

export const getProxySubscriptions = (token: string) =>
  request<ProxySubscriptionSettings>('/config/settings/proxy-subscriptions', {}, token);

export const saveProxySubscriptions = (token: string, update: ProxySubscriptionUpdate) =>
  request<ProxySubscriptionSettings>('/config/settings/proxy-subscriptions', {
    method: 'PUT',
    body: JSON.stringify(update),
  }, token, MEDIUM_TIMEOUT_MS);

export const refreshProxySubscriptions = (token: string) =>
  request<ProxySubscriptionSettings>('/config/settings/proxy-subscriptions/refresh', {
    method: 'POST',
  }, token, MEDIUM_TIMEOUT_MS);

export const testBotConnection = (token: string) =>
  request<{ success: boolean; message: string }>("/config/bot/test-connection", {
    method: "POST",
  }, token);

