import type { LegendEntry } from '../components/common/Legend'
import { GRAPH_PALETTE } from './graphStore'

/**
 * The map palette as legend entries — derived here, next to `GRAPH_PALETTE` (the graph's data
 * encoding, R33), so the table stays the single source and this is only its legend view. §3's law is
 * that a hue with no legend entry does not exist, so the seven categorical hues are keyed by name:
 * the table's **keys are these entries**. The swatch is the drawn mark (aria-hidden via `Legend`), the
 * name is the word, so the hue is never the only carrier.
 *
 * Consumers render it with `<Legend entries={paletteEntries} title="Map palette" />`.
 *
 * It lives in a `.tsx` module with no components (it builds a ReactNode swatch) because a component
 * module may not also export a value — `react-refresh/only-export-components`.
 */
export const paletteEntries: LegendEntry[] = Object.entries(GRAPH_PALETTE).map(([label, color]) => ({
  label,
  symbol: <span className="inline-block size-2.5 rounded-[2px]" style={{ backgroundColor: color }} />,
}))
