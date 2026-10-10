import { fetchWithAuth, getAuthToken, request, requestBlob } from './core'

const PATH = '/appearance/hero-image'
const SETTINGS_PATH = '/appearance/hero-settings'
export const MAX_HERO_IMAGE_BYTES = 2 * 1024 * 1024

export interface HeroSettings {
  present: boolean
  position_x: number
  position_y: number
}

export function getHeroImage(): Promise<Blob> {
  return requestBlob(PATH, {}, getAuthToken())
}

export async function uploadHeroImage(file: File): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  await fetchWithAuth(PATH, {}, { method: 'PUT', body: form }, getAuthToken())
}

export async function deleteHeroImage(): Promise<void> {
  await request(PATH, { method: 'DELETE' }, getAuthToken())
}

export function getHeroSettings(): Promise<HeroSettings> {
  return request<HeroSettings>(SETTINGS_PATH, {}, getAuthToken())
}

export function saveHeroSettings(position_x: number, position_y: number): Promise<HeroSettings> {
  return request<HeroSettings>(SETTINGS_PATH, {
    method: 'PUT',
    body: JSON.stringify({ position_x, position_y }),
  }, getAuthToken())
}
