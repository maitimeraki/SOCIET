import { describe, expect, it } from 'vitest'
import { mirrorScroll, shouldMirror } from './syncScroll'

const box = (scrollTop: number, scrollHeight: number, clientHeight = 100) => ({ scrollTop, scrollHeight, clientHeight })

describe('the two sides of the split', () => {
  it('mirrors the progress, not the pixels', () => {
    // The output has 900px of travel (1000 tall in a 100 tall window); the map has 300px.
    // 400px of the output's 900px journey is 4/9, so the map takes 4/9 of its own 300px range.
    const target = mirrorScroll(box(400, 1000), box(0, 400))
    expect(target).toBe(133)
  })

  it('is zero when the source cannot scroll', () => {
    expect(mirrorScroll(box(0, 100), box(0, 400))).toBe(0)
  })

  it('is zero when the target cannot scroll', () => {
    expect(mirrorScroll(box(400, 1000), box(0, 100))).toBe(0)
  })

  it('is the far end when the source is scrolled to its end', () => {
    expect(mirrorScroll(box(900, 1000), box(0, 400))).toBe(300)
  })
})

describe('the 1px tolerance guard', () => {
  it('lets a one-pixel difference stand, so the sides cannot chase each other', () => {
    expect(shouldMirror(100, 101)).toBe(false)
    expect(shouldMirror(101, 100)).toBe(false)
    expect(shouldMirror(100, 100)).toBe(false)
  })

  it('moves the target once the difference is more than a pixel', () => {
    expect(shouldMirror(100, 102)).toBe(true)
    expect(shouldMirror(102, 100)).toBe(true)
  })
})
