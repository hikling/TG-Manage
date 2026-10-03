/** Shared account and API error types. */
export type TokenResponse = { access_token: string; token_type: string }
export interface AccountUiItem {
  id: string
  name: string
  remark?: string | null
  status: string
  message: string
  avatarUrl: string
  raw: import('./api').AccountInfo
}

// ─── API 错误类型 ───
export interface ApiError extends Error {
  status?: number;
  code?: string;
}

// FastAPI 校验错误结构
export interface FastApiValidationError {
  loc: string[];
  msg: string;
  type: string;
}

// ─── 工具函数 ───

/** 常见 API / 网络错误码 → 默认英文文案（无 i18n 时兜底） */
const API_ERROR_CODE_MESSAGES: Record<string, string> = {
  NETWORK_TIMEOUT: 'Request timed out',
  NETWORK_ABORTED: 'Request cancelled',
  NETWORK_ERROR: 'Network error',
  ACCOUNT_SESSION_INVALID: 'Account session invalid, please re-login',
  TASK_LOG_NOT_FOUND: 'Task log not found',
  LOGIN_LOG_NOT_FOUND: 'Login log not found',
  INVALID_DATE_FILTER: 'Invalid date filter',
  LEGACY_TASKS_READONLY:
    '旧任务接口已移除，请使用 TeleBox 任务编排',
  TASK_NOT_FOUND: 'Task not found',
  ACCOUNT_NOT_FOUND: 'Account not found',
  RATE_LIMITED: 'Too many requests, please try later',
  INVALID_USERNAME_OR_PASSWORD: 'Invalid username or password',
  TOTP_REQUIRED_OR_INVALID: '2FA code invalid or missing',
  WEBDAV_NOT_CONFIGURED: 'WebDAV is not configured',
  BACKUP_EMPTY: 'Nothing to back up',
  CONFIG_JSON_EMPTY: 'Import configuration cannot be empty',
  AI_KEY_DECRYPT_FAILED: 'API Key decrypt failed; check APP_SECRET_KEY and re-save',
  CONFIG_IMPORT_FAILED: 'Config import failed',
  CLEAR_LOGS_FAILED: 'Failed to clear logs',
  JOB_NOT_FOUND: 'Job not found',
  JOB_NOT_CANCELABLE: 'Job cannot be cancelled (missing or already finished)',
  SESSION_PASSWORD_NEEDED: 'Two-step verification enabled; enter the 2FA password',
  PASSWORD_HASH_INVALID: 'Incorrect 2FA password',
  TASK_EXPORT_FAILED: 'Failed to export task',
  TASK_CONFIG_INVALID: 'Invalid task config',
  TASK_IMPORT_FAILED: 'Failed to import task',
  CONFIG_EXPORT_FAILED: 'Failed to export configs',
  TASK_DELETE_FAILED: 'Failed to delete task',
  AI_CONFIG_READ_FAILED: 'Failed to read AI config',
  AI_CONFIG_SAVE_FAILED: 'Failed to save AI config',
  AI_CONFIG_DELETE_FAILED: 'Failed to delete AI config',
  SETTINGS_READ_FAILED: 'Failed to read settings',
  SETTINGS_SAVE_FAILED: 'Failed to save settings',
  TG_CONFIG_READ_FAILED: 'Failed to read Telegram config',
  TG_CONFIG_SAVE_FAILED: 'Failed to save Telegram config',
  TG_CONFIG_RESET_FAILED: 'Failed to reset Telegram config',
  API_CREDENTIALS_REQUIRED: 'api_id and api_hash are required',
  API_ID_INVALID: 'api_id must be a positive integer',
  DATA_DIR_NOT_WRITABLE: 'Data directory is not writable',
}


const CODE_LIKE = /^[A-Z][A-Z0-9_]{2,}$/

/**
 * 从未知错误提取稳定错误码（优先 ApiError.code，其次 message/detail 若为 CODE 形态）。
 */
export function getErrorCode(e: unknown): string | undefined {
  if (e && typeof e === 'object') {
    const record = e as Record<string, unknown>
    if (typeof record.code === 'string' && record.code.trim()) {
      return record.code.trim()
    }
    if (typeof record.error_code === 'string' && record.error_code.trim()) {
      return record.error_code.trim()
    }
  }
  if (e instanceof Error) {
    const msg = (e.message || '').trim()
    if (CODE_LIKE.test(msg)) return msg
  }
  if (typeof e === 'string') {
    const msg = e.trim()
    if (CODE_LIKE.test(msg)) return msg
  }
  if (e && typeof e === 'object') {
    const record = e as Record<string, unknown>
    if (typeof record.detail === 'string' && CODE_LIKE.test(record.detail.trim())) {
      return record.detail.trim()
    }
    if (typeof record.message === 'string' && CODE_LIKE.test(record.message.trim())) {
      return record.message.trim()
    }
  }
  return undefined
}

/**
 * 超长错误文案截断：未知错误对象的 message/detail/序列化结果都可能
 * 携带长堆栈或嵌套字段，统一截断避免 toast 刷屏。
 */
const MAX_ERROR_MESSAGE_LENGTH = 200

function truncateErrorMessage(text: string): string {
  return text.length > MAX_ERROR_MESSAGE_LENGTH
    ? `${text.slice(0, MAX_ERROR_MESSAGE_LENGTH)}…`
    : text
}

/**
 * 从未知错误值中提取可读消息。
 * 空字符串 / 空白消息回退为默认文案，避免 toast 出现空白提示。
 * 已知错误码映射为可读英文；UI 可用 getErrorCode + i18n 再覆盖。
 */
export function getErrorMessage(e: unknown, fallback = 'Unknown error'): string {
  const code = getErrorCode(e)
  if (code && API_ERROR_CODE_MESSAGES[code]) {
    return API_ERROR_CODE_MESSAGES[code]
  }

  if (typeof e === 'string' && e.trim()) {
    return truncateErrorMessage(e.trim())
  }

  // 410 旧接口只读：detail 常为长英文说明，压缩展示
  if (e && typeof e === 'object') {
    const status = (e as ApiError).status
    const msg =
      e instanceof Error
        ? (e.message || '').trim()
        : typeof (e as Record<string, unknown>).detail === 'string'
          ? String((e as Record<string, unknown>).detail).trim()
          : ''
    if (
      status === 410 ||
      /legacy.*(read-?only|removed)|APP_LEGACY_TASKS_READONLY|LEGACY_EVENTS_LOGS_REMOVED/i.test(
        msg,
      )
    ) {
      return API_ERROR_CODE_MESSAGES.LEGACY_TASKS_READONLY
    }
  }

  if (e instanceof Error) {
    const msg = (e.message || '').trim()
    return msg ? truncateErrorMessage(msg) : fallback
  }
  if (typeof e === 'string') {
    const msg = e.trim()
    return msg ? truncateErrorMessage(msg) : fallback
  }
  if (e && typeof e === 'object') {
    const record = e as Record<string, unknown>
    if (typeof record.message === 'string' && record.message.trim()) {
      return truncateErrorMessage(record.message.trim())
    }
    if (typeof record.detail === 'string' && record.detail.trim()) {
      return truncateErrorMessage(record.detail.trim())
    }
    if (Array.isArray(record.detail) && record.detail.length > 0) {
      const msgs = record.detail
        .map((item) => {
          if (!item || typeof item !== 'object') return String(item || '')
          const rec = item as Record<string, unknown>
          const loc = Array.isArray(rec.loc) && rec.loc.length > 0 ? String(rec.loc[rec.loc.length - 1]) : ''
          const prefix = loc ? (loc + ': ') : ''
          const msg = typeof rec.msg === 'string' ? rec.msg.trim() : JSON.stringify(rec)
          return prefix + msg
        })
        .filter(Boolean)
      if (msgs.length > 0) {
        return truncateErrorMessage(msgs.join('; '))
      }
    }
    try {
      const serialized = JSON.stringify(e)
      if (serialized && serialized !== '{}') {
        return truncateErrorMessage(serialized)
      }
      return fallback
    } catch {
      return fallback
    }
  }
  return fallback
}

/**
 * 结合 i18n 翻译函数解析错误文案。
 * `t` 应能解析 `apiErrors.<CODE>`；未命中时回退 getErrorMessage。
 */
export function getLocalizedErrorMessage(
  e: unknown,
  t: (key: string) => string,
  fallback = 'Unknown error',
): string {
  const code = getErrorCode(e)
  if (code) {
    const key = `apiErrors.${code}`
    const localized = t(key)
    if (localized && localized !== key) return localized
  }
  // 410 旧任务
  if (e && typeof e === 'object' && (e as ApiError).status === 410) {
    const key = 'apiErrors.LEGACY_TASKS_READONLY'
    const localized = t(key)
    if (localized && localized !== key) return localized
  }
  return getErrorMessage(e, fallback)
}
