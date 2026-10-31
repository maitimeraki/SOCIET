export interface ScrollBox {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

/**
 * §10.3 — the two sides scroll together. The mapping is by *proportion*, not by pixels: the
 * sides have different content lengths, and a reader scrolling the output must see the map
 * move by the same fraction of its own journey.
 *
 * Returns the offset `to` should take. The caller only assigns it when it differs from the
 * current offset by more than a pixel, which is what stops the two panes from chasing each
 * other round a loop.
 */
export function mirrorScroll(from: ScrollBox, to: ScrollBox): number {
  const fromRange = from.scrollHeight - from.clientHeight
  const toRange = to.scrollHeight - to.clientHeight
  if (fromRange <= 0 || toRange <= 0) return 0
  const ratio = from.scrollTop / fromRange
  return Math.round(ratio * toRange)
}

/** True when the target has moved far enough to be worth assigning. */
export function shouldMirror(current: number, target: number): boolean {
  return Math.abs(current - target) > 1
}
