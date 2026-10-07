import { describe, expect, it } from 'vitest'
import { countryFlag } from '../lib/country-flag'

describe('account country flag', () => {
  it('renders the flag for a valid ISO region code', () => {
    expect(countryFlag('CN')).toBe('🇨🇳')
    expect(countryFlag('us')).toBe('🇺🇸')
  })

  it('does not invent a flag for an unknown region', () => {
    expect(countryFlag(null)).toBe('🌐')
    expect(countryFlag('001')).toBe('🌐')
  })
})
