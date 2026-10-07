/** Unicode regional-indicator flag for an ISO 3166-1 alpha-2 code. */
export function countryFlag(countryCode: string | null | undefined): string {
  if (!countryCode || !/^[A-Z]{2}$/i.test(countryCode)) return '🌐'
  return [...countryCode.toUpperCase()]
    .map(letter => String.fromCodePoint(0x1f1e6 + letter.charCodeAt(0) - 65))
    .join('')
}
