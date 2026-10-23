import './rules.css'

/**
 * §14.1 — the rule vocabulary. The rule is a **border on the content itself**, not a divider
 * element: the boundary belongs to the thing it separates, so the record's edge is one hairline
 * on one element and there is no extra node in the DOM.
 *
 * So `Rule` is a class vocabulary rather than a component — the same shape as `buttonClasses` in
 * `ui/Button.tsx`. `side` names the side the hairline is drawn on: `top`, `bottom`, `both` (a
 * block rule), `around` (every child after the first is ruled off from the one before it), and
 * the two vertical sides, `left` and `right` — the column hairline §14.2's auth layout draws
 * between its two columns.
 *
 * `tone` is the rule's colour: `light` (the default) is the light-surface rule token, and `dark`
 * is the map's own rule, for a hairline drawn on the one dark surface. The map's surface binds
 * the same token (`plot-ground` in `index.css`), so a rule on the map is the map's rule whether
 * the caller names the tone or the surface does.
 *
 * The hairlines live in `rules.css`, and the one colour is the rule token.
 */
export type RuleSide = 'top' | 'bottom' | 'both' | 'around' | 'left' | 'right'

/** The rule's ground: the light surfaces, or the map's own dark surface. */
export type RuleTone = 'light' | 'dark'

const RULE: Record<RuleSide, string> = {
  top: 'rule-t',
  bottom: 'rule-b',
  both: 'rule-y',
  around: 'divide-rule',
  left: 'rule-l',
  right: 'rule-r',
}

/**
 * The rule class for a side and a tone. The caller chooses the side; the hairline itself is the
 * kit's. `dark` adds the map's rule, so the same vocabulary draws the column hairline on the
 * light surface and the row hairline on the dark one.
 */
export function ruleClasses(side: RuleSide = 'top', tone: RuleTone = 'light'): string {
  return tone === 'dark' ? `${RULE[side]} rule-dark` : RULE[side]
}

// §14.1's acceptance row 12 asks every kit file for a default export. `Rule` is a vocabulary, not
// an element — the boundary belongs to the thing it separates, so no divider node is created — and
// the default export is that vocabulary itself.
export default ruleClasses
