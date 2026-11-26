const AVATAR_TONE_COUNT = 6
export const PASS_BANNER_TONE_COUNT = 20

export function accountAvatarToneClass(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i += 1) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  }
  return `avatar-tone--${Math.abs(hash) % AVATAR_TONE_COUNT}`
}

export function passBannerToneClass(index: number): string {
  const safe = ((index % PASS_BANNER_TONE_COUNT) + PASS_BANNER_TONE_COUNT) % PASS_BANNER_TONE_COUNT
  return `pass-tone--${safe}`
}
