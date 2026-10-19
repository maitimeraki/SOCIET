import { ArrowsLeftRight, ChatCircleText, CirclesThreePlus, UsersThree } from '@phosphor-icons/react'
import type { Icon } from '@phosphor-icons/react'
import type { LayerName } from './layers'

/**
 * §9.1 One drawn mark per layer, shared by the map pane's toggles and the entry-details drawer so
 * an entry read on the map and the same entry read in the drawer carry one mark. They come from the
 * same Phosphor set as the app's other controls; each is decorative — the adjacent word is the
 * control's name — so `LayerIcon` hides it from assistive tech at every size.
 */
const MARK: Record<LayerName, Icon> = {
  corpus: CirclesThreePlus,
  experts: UsersThree,
  opinions: ChatCircleText,
  connections: ArrowsLeftRight,
}

/** A layer's decorative mark, sized by its caller (16 in buttons, 14–16 in the drawer). */
export function LayerIcon({ layer, size }: { layer: LayerName; size: number }) {
  const Mark = MARK[layer]
  return <Mark size={size} aria-hidden="true" />
}
