import { create } from 'zustand'

/**
 * The entry or connection the customer opened from the map. `id` is the map store's own key — an
 * entry's id, or a connection's `source|target|kind` key.
 */
export interface MapSelection {
  kind: 'entry' | 'connection'
  id: string
}

interface SelectionStore {
  selection: MapSelection | null
  open: (selection: MapSelection) => void
  close: () => void
}

/**
 * The map's selection channel: the canvas writes it (a click on an entry or a connection) and the
 * entry-details drawer reads it. A channel rather than a prop, because the pane renders the canvas
 * as a child it cannot pass props to — and because the map is not its only writer (the pane's text
 * alternative opens the same entries). It holds which entry is open and no map data at all, so it is
 * not a second map store (D14).
 */
export const useSelectionStore = create<SelectionStore>((set) => ({
  selection: null,
  open: (selection) => set({ selection }),
  close: () => set({ selection: null }),
}))
