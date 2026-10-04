import { describe, it, expect } from 'vitest'
import {
  filterAccountsByQuery,
  isAccountHealthy,
  mapAccountInfoToUiItem,
} from '../lib/account-list-map'
import type { AccountInfo } from '../lib/api'

const labels = { loginExpired: '登录失效', checking: '检测中' }

describe('account-list-map', () => {
  it('recognizes connected sessions and keeps abnormal states visible', () => {
    expect(isAccountHealthy({ status: 'connected' })).toBe(true)
    expect(isAccountHealthy({ status: 'active' })).toBe(true)
    expect(isAccountHealthy({ status: 'connected', needs_relogin: true })).toBe(false)
    expect(isAccountHealthy({ status: 'connected', status_message: '额度不足' })).toBe(false)
    expect(isAccountHealthy({ status: 'checking' })).toBe(false)
    expect(isAccountHealthy({})).toBe(false)
    expect(mapAccountInfoToUiItem({ name: 'ok', status: 'connected' } as AccountInfo, labels).status).toBe('active')
    expect(mapAccountInfoToUiItem({ name: 'unknown' } as AccountInfo, labels).status).toBe('empty')
  })

  it('maps invalid and checking statuses', () => {
    const invalid = mapAccountInfoToUiItem(
      { name: 'a', needs_relogin: true, status: 'invalid' } as AccountInfo,
      labels,
    )
    expect(invalid.status).toBe('error')
    expect(invalid.message).toBe('登录失效')

    const checking = mapAccountInfoToUiItem(
      { name: 'b', status: 'checking' } as AccountInfo,
      labels,
    )
    expect(checking.status).toBe('empty')
    expect(checking.message).toBe('检测中')
  })

  it('filters by name remark message', () => {
    const list = [
      { name: 'alice', remark: '主号', message: '' },
      { name: 'bob', remark: '', message: '额度不足' },
    ]
    expect(filterAccountsByQuery(list, '主')).toHaveLength(1)
    expect(filterAccountsByQuery(list, '额度')).toHaveLength(1)
    expect(filterAccountsByQuery(list, '')).toHaveLength(2)
  })
})
