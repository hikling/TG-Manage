import { beforeEach, describe, expect, it, vi } from 'vitest'
import { exportAccountLoginBackup, importAccountLoginBackup } from '../lib/api/accounts'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

describe('account login backup API', () => {
  beforeEach(() => fetchMock.mockReset())

  it('exports encrypted bytes with the password in a POST body', async () => {
    const bytes = new Uint8Array([1, 2, 3, 4])
    fetchMock.mockResolvedValue(new Response(bytes, { status: 200 }))

    const blob = await exportAccountLoginBackup('token', 'a long backup password', true, true)

    expect(new Uint8Array(await blob.arrayBuffer())).toEqual(bytes)
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/accounts/login-backup/export')
    expect(options.method).toBe('POST')
    expect(options.headers).toMatchObject({
      Authorization: 'Bearer token',
      'Content-Type': 'application/json',
    })
    expect(JSON.parse(String(options.body))).toEqual({ password: 'a long backup password', allow_force_stop_container: true, allow_restore_server: true })
  })

  it('imports a file as multipart without forcing a JSON content type', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ restored: 2, skipped: 1 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    const file = new File(['encrypted'], 'accounts.tglogin')

    const result = await importAccountLoginBackup('token', file, 'a long backup password')

    expect(result).toEqual({ restored: 2, skipped: 1 })
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/accounts/login-backup/import')
    expect(options.method).toBe('POST')
    expect(options.headers).toMatchObject({ Authorization: 'Bearer token' })
    expect((options.headers as Record<string, string>)['Content-Type']).toBeUndefined()
    expect(options.body).toBeInstanceOf(FormData)
    const body = options.body as FormData
    expect(body.get('file')).toBe(file)
    expect(body.get('password')).toBe('a long backup password')
  })
})
