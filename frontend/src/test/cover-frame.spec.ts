import { describe, expect, it } from 'vitest'
import { clampCoverHeight, coverFrame, DEFAULT_COVER_HEIGHT, MAX_COVER_HEIGHT, MIN_COVER_HEIGHT } from '../lib/cover-frame'

describe('cover crop geometry', () => {
  it.each([[1600, 700], [300, 1200], [2000, 250]])('leaves drag space on both axes for a %sx%s image', (imageWidth, imageHeight) => {
    const frame = coverFrame(480, 210, imageWidth, imageHeight)
    expect(frame.overflowX).toBeGreaterThan(0)
    expect(frame.overflowY).toBeGreaterThan(0)
    expect(frame.width / frame.height).toBeCloseTo(imageWidth / imageHeight)
  })

  it('keeps the same crop across matching preview and dashboard ratios', () => {
    const preview = coverFrame(480, 210, 1200, 800)
    const dashboard = coverFrame(1440, 630, 1200, 800)
    expect(dashboard.width).toBeCloseTo(preview.width * 3)
    expect(dashboard.height).toBeCloseTo(preview.height * 3)
    expect(dashboard.overflowX).toBeCloseTo(preview.overflowX * 3)
    expect(dashboard.overflowY).toBeCloseTo(preview.overflowY * 3)
  })

  it('clamps dashboard cover height within valid bounds', () => {
    expect(clampCoverHeight(Number.NaN)).toBe(DEFAULT_COVER_HEIGHT)
    expect(clampCoverHeight(80)).toBe(MIN_COVER_HEIGHT)
    expect(clampCoverHeight(900)).toBe(MAX_COVER_HEIGHT)
    expect(clampCoverHeight(400)).toBe(400)
  })
})
