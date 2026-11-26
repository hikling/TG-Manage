export interface CoverFrame {
  width: number
  height: number
  overflowX: number
  overflowY: number
}

/** A modest fixed zoom keeps both framing controls effective for any image ratio. */
export function coverFrame(width: number, height: number, imageWidth: number, imageHeight: number): CoverFrame {
  if (width <= 0 || height <= 0 || imageWidth <= 0 || imageHeight <= 0) {
    return { width: 0, height: 0, overflowX: 0, overflowY: 0 }
  }
  const scale = Math.max(width / imageWidth, height / imageHeight) * 1.2
  const renderedWidth = imageWidth * scale
  const renderedHeight = imageHeight * scale
  return { width: renderedWidth, height: renderedHeight, overflowX: renderedWidth - width, overflowY: renderedHeight - height }
}

export const DEFAULT_COVER_HEIGHT = 360
export const MIN_COVER_HEIGHT = 160
export const MAX_COVER_HEIGHT = 520

export function clampCoverPosition(position: number): number {
  return Math.max(0, Math.min(100, Number.isFinite(position) ? position : 50))
}

export function clampCoverHeight(height: number): number {
  if (!Number.isFinite(height)) return DEFAULT_COVER_HEIGHT
  return Math.max(MIN_COVER_HEIGHT, Math.min(MAX_COVER_HEIGHT, Math.round(height)))
}
