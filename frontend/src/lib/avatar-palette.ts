const TONE_COUNT = 6

export function accountAvatarToneClass(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i += 1) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  }
  return `avatar-tone--${Math.abs(hash) % TONE_COUNT}`
}
