/**
 * localStorage 容错封装：禁用第三方存储/Safari 私密浏览等环境下，
 * 访问 localStorage 会抛 SecurityError；读写失败时读回退 null、写静默跳过，
 * 避免模块顶层或 store 初始化阶段应用直接崩溃。
 * 对齐 version-utils.ts 已有的 try/catch 容错范式。
 */
export function storageGet(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** 首次读取新键时迁移旧版浏览器偏好；写入失败则保留旧键供下次重试。 */
export function storageGetMigrated(key: string, legacyKey: string): string | null {
  const current = storageGet(key)
  if (current !== null) return current
  const legacy = storageGet(legacyKey)
  if (legacy === null) return null
  storageSet(key, legacy)
  if (storageGet(key) === legacy) storageRemove(legacyKey)
  return legacy
}

export function storageSet(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(key, value)
  } catch {
    /* 存储不可用时偏好不持久化，本次会话内状态仍生效 */
  }
}

export function storageRemove(key: string): void {
  try {
    if (typeof localStorage === 'undefined') return
    localStorage.removeItem(key)
  } catch {
    /* 同上 */
  }
}

export function storageGetJSON<T = unknown>(key: string, fallback: T | null = null): T | null {
  try {
    const raw = storageGet(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function storageSetJSON(key: string, value: unknown): void {
  try {
    storageSet(key, JSON.stringify(value))
  } catch {
    /* ignore */
  }
}

export function sessionGet(key: string): string | null {
  try {
    if (typeof sessionStorage === 'undefined') return null
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

export function sessionSet(key: string, value: string): void {
  try {
    if (typeof sessionStorage === 'undefined') return
    sessionStorage.setItem(key, value)
  } catch {
    /* ignore */
  }
}

export function sessionRemove(key: string): void {
  try {
    if (typeof sessionStorage === 'undefined') return
    sessionStorage.removeItem(key)
  } catch {
    /* ignore */
  }
}
