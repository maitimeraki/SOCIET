import './rules.css'

/**
 * §14.1 — the rule vocabulary. The rule is a **border on the content itself**, not a divider
 * element: the boundary belongs to the thing it separates, so the record's edge is one hairline
 * on one element and there is no extra node in the DOM.
 *
 * So `Rule` is a class vocabulary rather than a component — the same shape as `buttonClasses` in
 * `ui/Button.tsx`. `side` names the side the hairline is drawn on: `top`, `bottom`, `both` (a
 * block rule) or `around` (every child after the first is ruled off from the one before it).
 *
 * The hairlines live in `rules.css`, and the one colour is the rule token.
 */
export type RuleSide = 'top' | 'bottom' | 'both' | 'around'

const RULE: Record<RuleSide, string> = {
  top: 'rule-t',
  bottom: 'rule-b',
  both: 'rule-y',
  around: 'divide-rule',
}

/** The rule class for a side. The caller chooses the side; the hairline itself is the kit's. */
export function ruleClasses(side: RuleSide = 'top'): string {
  return RULE[side]
}
