import { fetchWithAuth, getAuthToken, request, requestBlob } from './core'

const PATH = '/appearance/hero-image'
export const MAX_HERO_IMAGE_BYTES = 5 * 1024 * 1024

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
