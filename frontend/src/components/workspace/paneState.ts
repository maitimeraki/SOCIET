/** §9 The three pane states. Split is the default; expanded lets the map fill the region; minimised
 *  turns the map into a live strip. */
export const PANE_STATES = ['split', 'expanded', 'minimised'] as const
export type PaneState = (typeof PANE_STATES)[number]

/** The pane geometry persists under the `chamber.*` convention (draftStore's persist name is
 *  `chamber.draft`), keyed by the run or session the workspace is showing. */
export const paneStorageKey = (mapId: string) => `chamber.workspace.${mapId}`

/**
 * The stored geometry wins; with nothing stored, a narrow viewport minimises by default (§9.3's phone
 * default) and everything wider splits. An unrecognised value never sticks — it falls back to the rule
 * rather than resurrecting a state we no longer have.
 */
export function paneStateFrom(stored: unknown, narrow = false): PaneState {
  return (PANE_STATES as readonly unknown[]).includes(stored)
    ? (stored as PaneState)
    : narrow
      ? 'minimised'
      : 'split'
}
