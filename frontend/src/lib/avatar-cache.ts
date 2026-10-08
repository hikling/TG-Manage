/**
 * 账号头像 ObjectURL 缓存：每个账号在同一会话内仅保留一个活动 blob 引用，
 * 替换或整体释放时回收旧 URL，避免账号列表反复刷新时泄漏 blob 内存。
 */
export class AvatarUrlCache {
  private urls = new Map<string, string>()
  private sizes = new Map<string, number>()
  private readonly maxBytes = 2 * 1024 * 1024

  /** 返回已缓存的 ObjectURL；未加载过则返回 undefined */
  get(name: string): string | undefined {
    return this.urls.get(name)
  }

  /** 登记新 URL；若该账号已有旧 URL 且不同，先回收旧引用 */
  canStore(name: string, size: number): boolean {
    const used = [...this.sizes.values()].reduce((sum, value) => sum + value, 0)
    return size >= 0 && used - (this.sizes.get(name) ?? 0) + size <= this.maxBytes
  }

  set(name: string, url: string, size = 0): void {
    const prev = this.urls.get(name)
    if (prev && prev !== url) {
      revoke(prev)
    }
    this.urls.set(name, url)
    this.sizes.set(name, size)
  }

  delete(name: string): void {
    const url = this.urls.get(name)
    if (url) revoke(url)
    this.urls.delete(name)
    this.sizes.delete(name)
  }

  retainOnly(names: Set<string>): void {
    for (const [name, url] of this.urls) {
      if (names.has(name)) continue
      revoke(url)
      this.urls.delete(name)
      this.sizes.delete(name)
    }
  }

  /** 组件卸载时统一回收全部 ObjectURL */
  release(): void {
    for (const url of this.urls.values()) {
      revoke(url)
    }
    this.urls.clear()
    this.sizes.clear()
  }
}

/** 账号检测后的头像请求代次：旧请求不得覆盖新缓存。 */
export class AvatarLoadGate {
  private versions = new Map<string, number>()
  private inFlight = new Map<string, number>()

  start(name: string): number | null {
    const version = this.versions.get(name) ?? 0
    if (this.inFlight.get(name) === version) return null
    this.inFlight.set(name, version)
    return version
  }

  isCurrent(name: string, version: number): boolean {
    return (this.versions.get(name) ?? 0) === version
  }

  invalidate(name: string): void {
    this.versions.set(name, (this.versions.get(name) ?? 0) + 1)
  }

  finish(name: string, version: number): void {
    if (this.inFlight.get(name) === version) this.inFlight.delete(name)
  }
}

function revoke(url: string): void {
  try {
    URL.revokeObjectURL(url)
  } catch {
    /* ignore */
  }
}
