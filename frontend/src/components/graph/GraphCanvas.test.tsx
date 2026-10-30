import { beforeEach, describe, expect, it, vi } from 'vitest'
import Graph from 'graphology'
import { renderToStaticMarkup } from 'react-dom/server'
import { useGraphStore } from '../../graph/graphStore'
import type { GraphEdge, GraphNode } from '../../graph/graphStore'
import { CORPUS_COLOR, EXPERT_COLOR, OPINION_TYPE, POSITION_COLORS, UNPOSITIONED_COLOR } from '../../graph/layers'
import { TEXT_FALLBACK_LIMIT, graphTextFallback } from '../../graph/graphText'
import {
  BLOOM_MS,
  DIM_SIZE_RATIO,
  GraphLegend,
  HOVER_MS,
  MAX_ANIMATED_NODES,
  MAX_LABELLED_NODES,
  SIGMA_SETTINGS,
  bloomScale,
  dimEntryColor,
  drawNodeLabel,
  entryOverride,
  graphAriaLabel,
  graphStatusMessage,
  graphStreamPhase,
  hoverDimmedEntries,
  hoverLevel,
  rampColorAt,
  seedPosition,
  shouldAnimateLayout,
  shouldBloom,
  showEdgeLabels,
  showNodeLabels,
  simplifiedViewNotice,
  syncGraph,
} from './GraphCanvas'
// §13 — the one copy-law guard. The canvas binds WebGL under Node and cannot be rendered in tests,
// so its customer-visible copy is checked through the pure string helpers it renders from instead.
import { BANNED_TERMS } from '../../test/copyLaw'

// No jsdom / no testing-library in this repo: the canvas is exercised through its
// pure sync function. React/Sigma never mount, so mock the one DOM-bound import.
vi.mock('@react-sigma/core', () => ({ SigmaContainer: () => null, useSigma: () => null }))

// The renderer's module-level colours are read off the document root, so the one wiring test that
// must see a real token (the label's sampled strokeStyle) gets the shipped values from a two-member
// plain object — not jsdom. `surveyColor` only reads `document.documentElement` and
// `getComputedStyle`; hoisted so it runs before GraphCanvas is imported.
vi.hoisted(() => {
  const tokens: Record<string, string> = {
    '--color-map-ground-2': '#16223D',
    '--color-map-ground': '#070C16',
    '--color-map-ink': '#E2E8F0',
    '--color-map-ink-2': '#94A3B8',
    '--color-map-accent': '#D9A8E2',
  }
  ;(globalThis as unknown as { document: unknown }).document = { documentElement: {} }
  ;(globalThis as unknown as { getComputedStyle: unknown }).getComputedStyle = () => ({
    getPropertyValue: (token: string) => tokens[token] ?? '',
  })
})

const byId = (...nodes: GraphNode[]): Record<string, GraphNode> =>
  Object.fromEntries(nodes.map((node) => [node.id, node]))

describe('SIGMA_SETTINGS', () => {
  it('allows the hidden container the minimised pane mounts, so the phone page cannot crash', () => {
    expect(SIGMA_SETTINGS.allowInvalidContainer).toBe(true)
  })
})

describe('syncGraph', () => {
  it('mirrors the store nodes and edges into the graphology instance', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
    )
    const edges: Record<string, GraphEdge> = {
      'a|b|POWERS': { source: 'a', target: 'b', label: 'POWERS' },
    }

    syncGraph(graph, nodes, edges)

    expect(graph.order).toBe(2)
    expect(graph.size).toBe(1)
  })

  it('colours each entry by its kind — the material blue, an expert’s luminous white', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'ds-1:steel tariffs', label: 'Steel tariffs', type: 'Topic' },
      { id: 'ds-1:D. Weber', label: 'D. Weber', type: 'Expert' },
    )

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('ds-1:steel tariffs', 'color')).toBe(CORPUS_COLOR)
    expect(graph.getNodeAttribute('ds-1:D. Weber', 'color')).toBe(EXPERT_COLOR)
  })

  it('colours an opinion by the position the backend stored with it (§2.4)', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'o+', label: '+', type: OPINION_TYPE, stance: 'POSITIVE' },
      { id: 'o-', label: '-', type: OPINION_TYPE, stance: 'NEGATIVE' },
    )

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('o+', 'color')).toBe(POSITION_COLORS.POSITIVE)
    expect(graph.getNodeAttribute('o-', 'color')).toBe(POSITION_COLORS.NEGATIVE)
  })

  it('colours an opinion whose position is not recorded in the neutral fallback, never a position’s hue', () => {
    const graph = new Graph({ multi: true })
    syncGraph(graph, byId({ id: 'o', label: 'D. Weber · pass 1', type: OPINION_TYPE }), {})

    const color = graph.getNodeAttribute('o', 'color') as string
    expect(color).toBe(UNPOSITIONED_COLOR)
    expect(Object.values(POSITION_COLORS)).not.toContain(color)
  })

  it('keeps ONE node when a repeated id arrives', () => {
    const graph = new Graph({ multi: true })
    syncGraph(graph, byId({ id: 'a', label: 'Glucose', type: 'Molecule' }), {})
    syncGraph(graph, byId({ id: 'a', label: 'Glucose (revised)', type: 'Molecule' }), {})

    expect(graph.order).toBe(1)
    expect(graph.getNodeAttribute('a', 'label')).toBe('Glucose (revised)')
  })

  it('seeds every added node with a finite position so Sigma never sees a positionless node', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
      { id: 'c', label: 'ATP', type: 'Molecule' },
    )

    syncGraph(graph, nodes, {})

    for (const id of ['a', 'b', 'c']) {
      expect(Number.isFinite(graph.getNodeAttribute(id, 'x'))).toBe(true)
      expect(Number.isFinite(graph.getNodeAttribute(id, 'y'))).toBe(true)
    }
  })

  it('keeps a node position once it has settled (a re-sync does not re-seed it)', () => {
    const graph = new Graph({ multi: true })
    syncGraph(graph, byId({ id: 'a', label: 'A', type: 'X' }), {})
    graph.setNodeAttribute('a', 'x', 42)

    syncGraph(graph, byId({ id: 'a', label: 'A', type: 'X' }), {})

    expect(graph.getNodeAttribute('a', 'x')).toBe(42)
  })

  it('drops nodes and edges the store no longer holds (snapshot reset)', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'A', type: 'X' },
      { id: 'b', label: 'B', type: 'Y' },
    )
    syncGraph(graph, nodes, { 'a|b|R': { source: 'a', target: 'b', label: 'R' } })

    syncGraph(graph, byId({ id: 'b', label: 'B', type: 'Y' }), {})

    expect(graph.order).toBe(1)
    expect(graph.hasNode('a')).toBe(false)
    expect(graph.size).toBe(0)
  })

  it('keeps two edges linking the same nodes with different labels (multi graph)', () => {
    // Regression: edge identity is `source|target|label`, so two chunks routinely connect the
    // same pair with different labels. A SIMPLE graphology graph throws UsageGraphError on the
    // second addEdgeWithKey, which crashed the sync effect and blanked the page.
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Eu ai act', type: 'Regulation' },
      { id: 'b', label: 'Autonomous warehouse robotics', type: 'Technology' },
    )
    const edges: Record<string, GraphEdge> = {
      'a|b|CLASSIFIES_AS': { source: 'a', target: 'b', label: 'CLASSIFIES_AS' },
      'a|b|MANDATES': { source: 'a', target: 'b', label: 'MANDATES' },
    }

    expect(() => syncGraph(graph, nodes, edges)).not.toThrow()
    expect(graph.size).toBe(2)
    expect(graph.hasEdge('a|b|CLASSIFIES_AS')).toBe(true)
    expect(graph.hasEdge('a|b|MANDATES')).toBe(true)
  })
})

describe('large-graph guard', () => {
  it('animates the layout up to the ceiling and freezes it above', () => {
    expect(shouldAnimateLayout(300)).toBe(true)
    expect(shouldAnimateLayout(MAX_ANIMATED_NODES)).toBe(true)
    expect(shouldAnimateLayout(1600)).toBe(false)
  })

  it('shows node labels up to the label ceiling and hides them above', () => {
    expect(showNodeLabels(300)).toBe(true)
    expect(showNodeLabels(MAX_LABELLED_NODES)).toBe(true)
    expect(showNodeLabels(1600)).toBe(false)
  })

  it('shows edge labels up to the animation ceiling and hides them above', () => {
    expect(showEdgeLabels(300)).toBe(true)
    expect(showEdgeLabels(1600)).toBe(false)
  })

  it('offers the simplified-view notice only while degrading', () => {
    expect(simplifiedViewNotice(300)).toBeNull()
    expect(simplifiedViewNotice(1600)).toBe('showing simplified view (1600 entries)')
  })

  it('drops node labels from the graph attributes above the ceiling', () => {
    const graph = new Graph({ multi: true })
    const nodes: Record<string, GraphNode> = {}
    for (let i = 0; i < 1600; i++) nodes[`n${i}`] = { id: `n${i}`, label: `Node ${i}`, type: 'Thing' }

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('n0', 'label')).toBeUndefined()
  })

  it('keeps node labels for a graph under the ceiling', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'Respiration', type: 'Process' },
    )

    syncGraph(graph, nodes, {})

    expect(graph.getNodeAttribute('a', 'label')).toBe('Glucose')
  })

  it('never sets an edge label attribute — edge labels stay off', () => {
    const graph = new Graph({ multi: true })
    const nodes = byId(
      { id: 'a', label: 'Glucose', type: 'Molecule' },
      { id: 'b', label: 'ATP', type: 'Molecule' },
    )
    const edges: Record<string, GraphEdge> = { 'a|b|POWERS': { source: 'a', target: 'b', label: 'POWERS' } }

    syncGraph(graph, nodes, edges)

    expect(graph.getEdgeAttribute('a|b|POWERS', 'label')).toBeUndefined()
  })
})

/* ── The ramp sampler and the hover/bloom dynamics (§12.4 Wave 2, §14.4 LIVE) ─────────────────── */

const RAMP_LIT = '#16223D'
const RAMP_DEEP = '#070C16'
const MAP_INK_TOK = '#E2E8F0'
const MAP_INK_2_TOK = '#94A3B8'
/** The dim blend's floor — `--color-map-ink-2`, read off the document root in the renderer. */
const DIM_FLOOR = '#94A3B8'
/** The lit end of the map ramp — the worst ground a dimmed entry can sit on. */
const LIT_GROUND = '#16223D'

/** The channels of a `#rrggbb` or `rgb(r, g, b)` colour. */
const channels = (color: string): [number, number, number] => {
  const asRgb = color.match(/^rgb\((\d+), (\d+), (\d+)\)$/)
  if (asRgb) return [Number(asRgb[1]), Number(asRgb[2]), Number(asRgb[3])]
  const asHex = color.match(/^#([0-9a-f]{6})$/i)
  if (!asHex) throw new Error(`not a colour: ${color}`)
  const value = parseInt(asHex[1], 16)
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255]
}

/** WCAG 2.2 relative luminance. */
const luminance = (color: string): number => {
  const [r, g, b] = channels(color)
  const channel = (value: number) => {
    const s = value / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

const contrast = (a: string, b: string): number => {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

/** CIE lightness: L* = 116·Y^(1/3) − 16 above the knee, 903.3·Y below it. */
const lightness = (color: string): number => {
  const y = luminance(color)
  return y > 0.008856 ? 116 * Math.cbrt(y) - 16 : 903.3 * y
}

describe('rampColorAt — the halo is the paint (§12.4 Wave 2)', () => {
  const W = 1000
  const H = 500

  it('samples the lit centre, the midpoint of the ray and the deep floor', () => {
    expect(rampColorAt(W / 2, 0, W, H, RAMP_LIT, RAMP_DEEP)).toBe('rgb(22, 34, 61)')
    expect(rampColorAt(W / 2, 0.36 * H, W, H, RAMP_LIT, RAMP_DEEP)).toBe('rgb(15, 23, 42)')
    expect(rampColorAt(W / 2, 0.72 * H, W, H, RAMP_LIT, RAMP_DEEP)).toBe('rgb(7, 12, 22)')
  })

  it('holds the deep floor past the 72% stop, at every corner', () => {
    expect(rampColorAt(0, H, W, H, RAMP_LIT, RAMP_DEEP)).toBe('rgb(7, 12, 22)')
    expect(rampColorAt(W, H, W, H, RAMP_LIT, RAMP_DEEP)).toBe('rgb(7, 12, 22)')
    expect(rampColorAt(W / 2, H * 4, W, H, RAMP_LIT, RAMP_DEEP)).toBe('rgb(7, 12, 22)')
  })

  it('reads the far stop in a box that has no size yet (the minimised host)', () => {
    expect(rampColorAt(10, 10, 0, 0, RAMP_LIT, RAMP_DEEP)).toBe('rgb(7, 12, 22)')
  })

  it('meets the three contrast checks at every sample', () => {
    const samples = [
      { point: [W / 2, 0] as const, paint: '#16223d' },
      { point: [W / 2, 0.36 * H] as const, paint: '#0f172a' },
      { point: [W / 2, 0.72 * H] as const, paint: '#070c16' },
      { point: [0, H] as const, paint: '#070c16' },
    ]
    for (const { point, paint } of samples) {
      const halo = rampColorAt(point[0], point[1], W, H, RAMP_LIT, RAMP_DEEP)
      // The halo IS the paint — never a plate (≤ 1.20:1).
      expect(contrast(halo, paint), `halo vs paint at ${point}`).toBeLessThanOrEqual(1.2)
      // The label and the edge stay legible over it.
      expect(contrast(MAP_INK_TOK, halo), `label ink vs halo at ${point}`).toBeGreaterThanOrEqual(4.5)
      expect(contrast(MAP_INK_2_TOK, halo), `edge ink vs halo at ${point}`).toBeGreaterThanOrEqual(3)
    }
  })

  it('tracks the ramp range: the two extremes are at least 8 L* apart', () => {
    const lit = rampColorAt(W / 2, 0, W, H, RAMP_LIT, RAMP_DEEP)
    const deep = rampColorAt(W / 2, 0.72 * H, W, H, RAMP_LIT, RAMP_DEEP)
    expect(Math.abs(lightness(deep) - lightness(lit))).toBeGreaterThanOrEqual(8)
  })
})

describe('the hover reducer — the neighbourhood keeps its strength (§12.4 Wave 2)', () => {
  const build = () => {
    const graph = new Graph({ multi: true })
    graph.addNode('hub', { color: CORPUS_COLOR, size: 7, x: 0, y: 0 })
    graph.addNode('near-a', { color: POSITION_COLORS.POSITIVE, size: 7 })
    graph.addNode('near-b', { color: POSITION_COLORS.NEGATIVE, size: 7 })
    graph.addNode('far-corpus', { color: CORPUS_COLOR, size: 7 })
    graph.addNode('far-expert', { color: EXPERT_COLOR, size: 7 })
    graph.addNode('far-pos', { color: POSITION_COLORS.POSITIVE, size: 7 })
    graph.addNode('far-neu', { color: POSITION_COLORS.NEUTRAL, size: 7 })
    graph.addNode('far-amb', { color: POSITION_COLORS.AMBIVALENT, size: 7 })
    graph.addNode('far-neg', { color: POSITION_COLORS.NEGATIVE, size: 7 })
    graph.addNode('far-unpositioned', { color: UNPOSITIONED_COLOR, size: 7 })
    graph.addEdge('hub', 'near-a')
    graph.addEdge('hub', 'near-b')
    return graph
  }

  it('dims every entry outside the hovered entry’s neighbourhood, and nothing else', () => {
    const dimmed = hoverDimmedEntries(build(), 'hub', DIM_FLOOR)
    expect([...dimmed.keys()].sort()).toEqual(
      ['far-amb', 'far-corpus', 'far-expert', 'far-neg', 'far-neu', 'far-pos', 'far-unpositioned'].sort(),
    )
    expect(dimmed.has('hub')).toBe(false)
    expect(dimmed.has('near-a')).toBe(false)
    expect(dimmed.has('near-b')).toBe(false)
  })

  it('shrinks a dimmed entry — the shape carries the reduction beside the muted colour', () => {
    const dimmed = hoverDimmedEntries(build(), 'hub', DIM_FLOOR)
    expect(dimmed.get('far-expert')?.size).toBeCloseTo(7 * DIM_SIZE_RATIO)
  })

  it('never lets a dimmed entry fall under 3:1 against the lit end of the ramp', () => {
    const dimmed = hoverDimmedEntries(build(), 'hub', DIM_FLOOR)
    expect(dimmed.size).toBeGreaterThan(0)
    for (const [entry, override] of dimmed) {
      expect(contrast(override.color, LIT_GROUND), entry).toBeGreaterThanOrEqual(3)
    }
  })

  it('returns no override for an entry the graph does not hold', () => {
    expect(hoverDimmedEntries(build(), 'ghost', DIM_FLOOR).size).toBe(0)
  })

  it('blends a dimmed colour halfway toward the quiet ink', () => {
    expect(dimEntryColor(CORPUS_COLOR, DIM_FLOOR)).toBe('rgb(104, 147, 215)')
  })
})

describe('the bloom — once, in the grammar, and never a fade (§14.4 LIVE)', () => {
  it('is the grammar’s 560ms', () => {
    expect(BLOOM_MS).toBe(560)
  })

  it('rises to 1.28 and settles at 1 over 560ms', () => {
    expect(bloomScale(0)).toBe(0)
    expect(bloomScale(0.3 * BLOOM_MS)).toBeCloseTo(0.64)
    expect(bloomScale(0.6 * BLOOM_MS)).toBeCloseTo(1.28)
    expect(bloomScale(0.8 * BLOOM_MS)).toBeCloseTo(1.14)
    expect(bloomScale(BLOOM_MS)).toBe(1)
    expect(bloomScale(BLOOM_MS * 10)).toBe(1)
  })

  it('is simply there under prefers-reduced-motion: reduce', () => {
    expect(bloomScale(0, true)).toBe(1)
    expect(bloomScale(0.1 * BLOOM_MS, true)).toBe(1)
  })
})

describe('entryOverride — the reducer hands Sigma the whole node', () => {
  // Sigma replaces a node's attributes with the reducer's result rather than merging; anything left
  // out (x, y, type) makes the renderer throw. Pin the total-object contract.
  const data = { x: 12, y: 34, size: 7, color: '#3B82F6', label: 'Mill Street lease', type: 'circle' }
  const dim = { color: 'rgb(104, 147, 215)', size: 7 * DIM_SIZE_RATIO }

  it('returns the node untouched when nothing is dimmed or blooming', () => {
    expect(entryOverride(data, undefined, 0, undefined, 0)).toBe(data)
  })

  it('scales the size for a bloom without losing a single attribute', () => {
    const out = entryOverride(data, undefined, 0, 0, 0.3 * BLOOM_MS)
    expect(out.size).toBeCloseTo(7 * 0.64)
    expect(out).toMatchObject({ x: 12, y: 34, color: '#3B82F6', label: 'Mill Street lease', type: 'circle' })
  })

  it('blends colour and size by the hover level — the mid-transition value is strictly between', () => {
    const out = entryOverride(data, dim, 0.5, undefined, 0)
    expect(out.color).toBe('rgb(82, 139, 231)') // between #3B82F6 and rgb(104, 147, 215)
    expect(out.size).toBeCloseTo(7 + (7 * DIM_SIZE_RATIO - 7) * 0.5)
  })

  it('applies the dimmed colour and size at rest, with the bloom on top', () => {
    const out = entryOverride(data, dim, 1, 0, 0.6 * BLOOM_MS)
    expect(out.color).toBe('rgb(104, 147, 215)')
    expect(out.size).toBeCloseTo(7 * DIM_SIZE_RATIO * 1.28)
  })

  it('is simply full size under reduced motion', () => {
    expect(entryOverride(data, undefined, 0, 0, 0, true).size).toBe(7)
  })
})

describe('hoverLevel — the 120ms state curve (I1)', () => {
  it('runs from 0 to 1 over 120ms and holds at the endpoint', () => {
    expect(HOVER_MS).toBe(120)
    expect(hoverLevel(0)).toBe(0)
    expect(hoverLevel(HOVER_MS)).toBe(1)
    expect(hoverLevel(HOVER_MS * 4)).toBe(1)
    expect(hoverLevel(HOVER_MS / 2)).toBeGreaterThan(0)
    expect(hoverLevel(HOVER_MS / 2)).toBeLessThan(1)
  })

  it('is monotonic across the curve', () => {
    const samples = Array.from({ length: 13 }, (_, index) => hoverLevel((index / 12) * HOVER_MS))
    for (let index = 1; index < samples.length; index += 1) {
      expect(samples[index], `sample ${index}`).toBeGreaterThanOrEqual(samples[index - 1])
    }
    expect(samples[6]).toBeGreaterThan(samples[0])
    expect(samples[6]).toBeLessThan(samples[12])
  })

  it('jumps to the endpoint under prefers-reduced-motion: reduce', () => {
    expect(hoverLevel(0, true)).toBe(1)
    expect(hoverLevel(1, true)).toBe(1)
    expect(hoverLevel(HOVER_MS, true)).toBe(1)
  })
})

describe('shouldBloom — once per entry per graph instance (M3)', () => {
  it('blooms an id once and never again on the same graph', () => {
    const bloomed = new Set<string>()
    expect(shouldBloom(bloomed, 'entry-a')).toBe(true)
    bloomed.add('entry-a')
    expect(shouldBloom(bloomed, 'entry-a')).toBe(false)
  })

  it('blooms the same id again on a fresh graph instance', () => {
    const previousGraph = new Set<string>(['entry-a'])
    const freshGraph = new Set<string>()
    expect(shouldBloom(previousGraph, 'entry-a')).toBe(false)
    expect(shouldBloom(freshGraph, 'entry-a')).toBe(true)
  })
})

describe('drawNodeLabel', () => {
  const data = { x: 10, y: 20, size: 7, label: 'Glucose', color: '#000' }

  it('strokes a halo before filling, so an edge cannot cut through the label text', () => {
    const calls: string[] = []
    const context = {
      font: '',
      lineJoin: '',
      lineWidth: 0,
      strokeStyle: '',
      fillStyle: '',
      strokeText: () => calls.push('stroke'),
      fillText: () => calls.push('fill'),
    }
    const settings = { labelSize: 12, labelFont: 'X', labelWeight: '500', labelColor: { color: '#111111' } }

    drawNodeLabel(context as unknown as CanvasRenderingContext2D, data as never, settings as never)

    expect(calls).toEqual(['stroke', 'fill'])
    expect(context.fillStyle).toBe('#111111')
  })

  it('strikes the halo in the ramp colour at the label’s position, not a flat tone', () => {
    const context = {
      font: '',
      lineJoin: '',
      lineWidth: 0,
      strokeStyle: '',
      fillStyle: '',
      // Sigma's label canvas is scaled by the device pixel ratio; here one CSS px is one device px.
      canvas: { width: 200, height: 100 },
      getTransform: () => ({ a: 1 }),
      strokeText: () => {},
      fillText: () => {},
    }
    const settings = { labelSize: 12, labelFont: 'X', labelWeight: '500', labelColor: { color: '#111111' } }
    // The label's point: x + size + 3 = 20, y + labelSize / 3 = 24.
    drawNodeLabel(context as unknown as CanvasRenderingContext2D, data as never, settings as never)

    expect(context.strokeStyle).toBe(rampColorAt(20, 24, 200, 100, '#16223D', '#070C16'))
  })

  it('draws nothing for a node without a label', () => {
    const calls: string[] = []
    const context = { strokeText: () => calls.push('stroke'), fillText: () => calls.push('fill') }
    const settings = { labelSize: 12, labelFont: 'X', labelWeight: '500', labelColor: { color: '#111111' } }

    drawNodeLabel(context as unknown as CanvasRenderingContext2D, { ...data, label: undefined } as never, settings as never)

    expect(calls).toEqual([])
  })
})

describe('seedPosition', () => {
  it('spreads successive nodes apart rather than stacking them at the origin', () => {
    const a = seedPosition(0)
    const b = seedPosition(1)
    expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(0)
  })

  it('is deterministic for a given index', () => {
    expect(seedPosition(5)).toEqual(seedPosition(5))
  })
})

describe('graphAriaLabel', () => {
  it('counts the nodes, edges and entity types', () => {
    expect(graphAriaLabel(12, 8, 3)).toBe('Your map: 12 entries, 8 connections, 3 entity types')
  })

  it('pluralises a lone node, edge and entity type', () => {
    expect(graphAriaLabel(1, 1, 1)).toBe('Your map: 1 entry, 1 connection, 1 entity type')
  })

  it('reads as an empty graph before anything arrives', () => {
    expect(graphAriaLabel(0, 0, 0)).toBe('Your map: 0 entries, 0 connections, 0 entity types')
  })
})

describe('graphStreamPhase / graphStatusMessage', () => {
  it('waits for the first chunk while the graph is empty', () => {
    expect(graphStreamPhase(0, 'connecting', false)).toBe('waiting')
    expect(graphStreamPhase(0, 'open', false)).toBe('waiting')
    expect(graphStatusMessage(0, 'open', false)).toBe('Waiting for the first section…')
  })

  it('streams silently once a node has arrived', () => {
    expect(graphStreamPhase(3, 'open', false)).toBe('streaming')
    expect(graphStatusMessage(3, 'open', false)).toBeNull()
  })

  it('reports failure when the socket closes before done', () => {
    expect(graphStreamPhase(5, 'closed', false)).toBe('failed')
    expect(graphStatusMessage(5, 'closed', false)).toBe('The live map stream failed — the map stays as the last snapshot.')
  })

  it('reports the ended state on a done frame, even with zero nodes', () => {
    expect(graphStreamPhase(0, 'closed', true)).toBe('ended')
    expect(graphStatusMessage(0, 'closed', true)).toBe('The live map stream has ended.')
  })
})

describe('the copy law (§13) governs every string the canvas renders (§8.5 — WebGL-free)', () => {
  it('renders no banned word in the img label, the status overlay or the simplified-view notice', () => {
    const rendered = [
      graphAriaLabel(12, 8, 3),
      graphStatusMessage(0, 'open', false),
      graphStatusMessage(5, 'closed', false),
      graphStatusMessage(0, 'closed', true),
      simplifiedViewNotice(1600),
    ].filter((line): line is string => line !== null)
    expect(rendered).not.toHaveLength(0)
    for (const line of rendered) expect(line).not.toMatch(BANNED_TERMS)
  })
})

describe('graphTextFallback', () => {
  const nodes: GraphNode[] = [
    { id: 'a', label: 'Glucose', type: 'Molecule' },
    { id: 'b', label: 'Respiration', type: 'Process' },
    { id: 'c', label: 'ATP', type: 'Molecule' },
  ]

  it('renders relations and standalone entities as text lines', () => {
    const edges: GraphEdge[] = [{ source: 'a', target: 'b', label: 'POWERS' }]

    const { lines, omitted } = graphTextFallback(nodes, edges, TEXT_FALLBACK_LIMIT)

    expect(lines).toEqual(['Glucose —POWERS→ Respiration', 'ATP (Molecule)'])
    expect(omitted).toBe(0)
  })

  it('caps the list at the limit and counts what it left out', () => {
    const edges: GraphEdge[] = [{ source: 'a', target: 'b', label: 'POWERS' }]

    const { lines, omitted } = graphTextFallback(nodes, edges, 1)

    expect(lines).toEqual(['Glucose —POWERS→ Respiration'])
    expect(omitted).toBe(1)
  })

  it('skips an edge whose endpoint is not in the store', () => {
    const edges: GraphEdge[] = [{ source: 'a', target: 'missing', label: 'POWERS' }]

    const { lines, omitted } = graphTextFallback(nodes, edges, TEXT_FALLBACK_LIMIT)

    expect(lines).toEqual(['Glucose (Molecule)', 'Respiration (Process)', 'ATP (Molecule)'])
    expect(omitted).toBe(0)
  })
})

describe('GraphLegend — the map’s key (§6, §9)', () => {
  it('names every colour the map draws, each with its own word', () => {
    const html = renderToStaticMarkup(<GraphLegend hasEntries />)

    for (const word of ['Corpus', 'Experts', 'POSITIVE', 'NEUTRAL', 'AMBIVALENT', 'NEGATIVE', 'No position']) {
      expect(html).toContain(word)
    }
    // The swatches carry the very hues the canvas paints, so the key and the map cannot drift.
    for (const color of [CORPUS_COLOR, EXPERT_COLOR, UNPOSITIONED_COLOR, ...Object.values(POSITION_COLORS)]) {
      expect(html).toContain(color)
    }
    // Every symbol is a drawn mark — an authored SVG for the stances, a Phosphor icon otherwise —
    // never a typographic glyph, and every mark is decorative beside its word.
    expect(html).toContain('<svg')
    expect(html).toContain('aria-hidden="true"')
  })

  it('draws nothing over a map holding no entry', () => {
    expect(renderToStaticMarkup(<GraphLegend hasEntries={false} />)).toBe('')
  })
})

// One store fed by two streams (D14): the corpus layer folds in from the graph stream, the expert
// and opinion layers fold in from the debate stream. The store is a module singleton — reset it
// between cases so counts are absolute.
describe('the one map, fed by both streams', () => {
  beforeEach(() => useGraphStore.setState({ nodes: {}, edges: {}, labels: [], version: 0 }))

  it('an agent event seats exactly one entry, keyed as the backend keys the person', () => {
    useGraphStore.getState().mergeExpert({ datasetId: 'ds-1', name: 'D. Weber' })

    expect(Object.keys(useGraphStore.getState().nodes)).toEqual(['ds-1:D. Weber'])
  })

  it('a commit seats one entry per written node and one connection per written link, keyed as the backend keyed them', () => {
    useGraphStore.getState().mergeOpinions(
      [
        { key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' },
        { key: 'ds-1:qh:1:M. Chen', label: 'Opinion', name: 'M. Chen · pass 1' },
      ],
      [
        { from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' },
        { from: 'ds-1:M. Chen', to: 'ds-1:qh:1:M. Chen', kind: 'STATED' },
      ],
    )

    const { nodes, edges } = useGraphStore.getState()
    expect([Object.keys(nodes), Object.keys(edges)]).toEqual([
      ['ds-1:qh:1:D. Weber', 'ds-1:qh:1:M. Chen'],
      ['ds-1:D. Weber|ds-1:qh:1:D. Weber|STATED', 'ds-1:M. Chen|ds-1:qh:1:M. Chen|STATED'],
    ])
  })

  it('keeps a written entry verbatim — its name is the label, its kind the type', () => {
    useGraphStore.getState().mergeOpinions(
      [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }],
      [],
    )

    const node = useGraphStore.getState().nodes['ds-1:qh:1:D. Weber']
    expect([node.label, node.type]).toEqual(['D. Weber · pass 1', 'Opinion'])
  })

  it('folding the same commit twice adds nothing the second time', () => {
    const nodes = [{ key: 'ds-1:qh:1:D. Weber', label: 'Opinion', name: 'D. Weber · pass 1' }]
    const links = [{ from: 'ds-1:D. Weber', to: 'ds-1:qh:1:D. Weber', kind: 'STATED' }]

    useGraphStore.getState().mergeOpinions(nodes, links)
    useGraphStore.getState().mergeOpinions(nodes, links)

    const { nodes: after, edges: afterEdges } = useGraphStore.getState()
    expect([Object.keys(after).length, Object.keys(afterEdges).length]).toEqual([1, 1])
  })

  it('the corpus layer and the expert layer share the one store, neither clearing the other', () => {
    useGraphStore.getState().mergeDelta({ nodes: [{ id: 'ds-1:steel tariffs', label: 'steel tariffs', type: 'Topic' }], edges: [] })
    useGraphStore.getState().mergeExpert({ datasetId: 'ds-1', name: 'D. Weber' })

    expect(Object.keys(useGraphStore.getState().nodes).sort()).toEqual(['ds-1:D. Weber', 'ds-1:steel tariffs'])
  })
})
