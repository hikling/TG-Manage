const AVATAR_TONES = [
  'linear-gradient(135deg, #3b82f6, #2563eb)',
  'linear-gradient(135deg, #10b981, #059669)',
  'linear-gradient(135deg, #8b5cf6, #7c3aed)',
  'linear-gradient(135deg, #f59e0b, #d97706)',
  'linear-gradient(135deg, #ec4899, #db2777)',
  'linear-gradient(135deg, #06b6d4, #0891b2)',
] as const

export function accountAvatarTone(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i += 1) {
    hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  }
  return AVATAR_TONES[Math.abs(hash) % AVATAR_TONES.length]!
}
