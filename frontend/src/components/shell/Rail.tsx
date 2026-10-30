import { Link, NavLink } from 'react-router-dom'
import { CheckCircle, Plus, SquaresFour } from '@phosphor-icons/react'
import { useAuthStore } from '../../auth/authStore'
import HealthDot from './HealthDot'
import { buttonClasses } from '../ui/Button'
import { ruleClasses } from '../ui/Rule'

/**
 * §7 The rail — the persistent left column: brand at its head, the new-decision action and the
 * three destinations in the middle, the account reading at its foot. 240px on wide screens, 64px
 * and icon-only below `lg`.
 *
 * The three destinations are the lifecycle's stages: Documents (what the account holds), Verdict
 * (the last answer) and Runs (the work behind it). `NavLink` sets `aria-current` for us, so the
 * active item is correct without a pathname comparison here.
 */
const ITEMS = [
  { to: '/documents', label: 'Documents', Icon: SquaresFour },
  { to: '/results', label: 'Verdict', Icon: CheckCircle },
  { to: '/runs', label: 'Runs', Icon: SquaresFour },
]

// §7 Rail item states — resting ink-2; hover a ground fill; active an accent-soft fill with a 3px
// accent left rule and ink at weight 500. The rule is a `::before` flush to the rail's own edge, so
// it does not indent with the item's padding.
//
// The active item's ICON takes the accent too: the accent-soft fill alone measures 1.035:1 against
// the rail, which the eye cannot find. The accent is on the mark, and the word stays ink.
const ITEM = 'relative flex min-h-11 items-center gap-3 px-3 py-2 font-ui text-body transition-colors duration-state'
const itemClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? `${ITEM} bg-accent-soft font-medium text-ink before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:bg-accent`
    : `${ITEM} text-ink-2 hover:bg-bone hover:text-ink`

/** The label is `sr-only` in the collapsed rail, so every item keeps an accessible name at 64px. */
const LABEL = 'sr-only lg:not-sr-only'

export default function Rail() {
  const email = useAuthStore((s) => s.user?.email ?? '')
  const initials = email.split('@')[0].slice(0, 2).toUpperCase()

  return (
    // The column. The `<nav>` holds the brand, the new-decision action and the sections; the
    // account foot is its sibling, not its child — a landmark jump to "Sections" must not land on
    // account or health chrome.
    <div className={`flex w-16 shrink-0 flex-col ${ruleClasses('right')} bg-sand lg:w-60`}>
      <nav aria-label="Sections" className="flex flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-2 px-2 lg:px-4">
          <Link
            to="/"
            className="flex min-h-11 min-w-11 items-center justify-center gap-2 text-ink lg:justify-start"
          >
            {/* §7 draws a diamond, not a logo — the glyph is the mark, the wordmark names the product. */}
            <span aria-hidden="true" className="font-display text-heading leading-none">
              ◆
            </span>
            <span className="sr-only font-ui text-body-sm font-semibold lg:not-sr-only">
              Societas
            </span>
          </Link>
        </div>

        <Link to="/new" className={buttonClasses('primary', 40, 'mx-3 mb-4 min-h-11 min-w-11 justify-center')}>
          <Plus size={16} aria-hidden="true" />
          <span className={LABEL}>New decision</span>
        </Link>

        <ul className="flex flex-1 flex-col gap-1">
          {ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} className={itemClass}>
                {({ isActive }) => (
                  <>
                    <span className={`flex w-4 shrink-0 justify-center ${isActive ? 'text-accent' : ''}`}>
                      <item.Icon size={16} aria-hidden="true" />
                    </span>
                    <span className={LABEL}>{item.label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className={`${ruleClasses('top')} pt-2`}>
        {/* 240px only: the reading's label text does not fit the 64px rail. */}
        <div className="hidden px-4 pb-2 lg:block">
          <HealthDot />
        </div>
        <div className="flex items-center gap-2 px-3 py-2">
          <span
            aria-hidden="true"
            className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-soft font-ui text-micro font-medium text-accent"
          >
            {initials}
          </span>
          <span className={`${LABEL} text-label text-ink-2`}>Account</span>
        </div>
      </div>
    </div>
  )
}
