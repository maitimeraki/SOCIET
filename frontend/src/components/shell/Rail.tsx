import { Link, NavLink } from 'react-router-dom'
import { Files, Gavel, SealCheck, UsersThree } from '@phosphor-icons/react'
import { useAuthStore } from '../../auth/authStore'
import HealthDot from './HealthDot'

/**
 * §7 The rail — the persistent left column: brand at its head, the four section items in the middle,
 * the account reading at its foot. 240px on wide screens, 64px and icon-only below `lg`.
 *
 * The label and the path deliberately differ (D16): "Documents" is customer copy, `/documents` is an
 * internal identifier exempt from the copy law (§13). `NavLink` sets `aria-current` for us, so the
 * active item is correct without a pathname comparison here.
 */
const SECTIONS = [
  { to: '/documents', label: 'Documents', Icon: Files },
  { to: '/runs', label: 'Decisions', Icon: Gavel },
  { to: '/results', label: 'Verdicts', Icon: SealCheck },
  { to: '/panel', label: 'Panel', Icon: UsersThree },
]

// §7 Rail item states — resting ink-2; hover a ground fill; active an accent-soft fill with a 3px
// accent left rule and ink at weight 500. The rule is a `::before` flush to the rail's own edge, so
// it does not indent with the item's padding.
const ITEM = 'relative flex items-center gap-3 px-3 py-2 font-titling text-body transition-colors'
const itemClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? `${ITEM} bg-accent-soft font-medium text-ink before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:bg-accent`
    : `${ITEM} text-ink-2 hover:bg-ground hover:text-ink`

/** The label is `sr-only` in the collapsed rail, so every item keeps an accessible name at 64px. */
const LABEL = 'sr-only lg:not-sr-only'

export default function Rail() {
  const email = useAuthStore((s) => s.user?.email ?? '')
  const initials = email.split('@')[0].slice(0, 2).toUpperCase()

  return (
    // The column. The `<nav>` holds only the sections; the account foot is its sibling, not its
    // child — a landmark jump to "Sections" must not land on account or health chrome.
    <div className="flex w-16 shrink-0 flex-col border-r border-border bg-ground-2 lg:w-60">
      <nav aria-label="Sections" className="flex flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-2 px-4">
          <Link to="/" className="flex items-center gap-2 text-ink">
            {/* §7 draws a diamond, not a logo — the glyph is the mark, the wordmark names the product. */}
            <span aria-hidden="true" className="font-titling text-title leading-none">
              ◆
            </span>
            <span className="sr-only font-titling text-heading font-semibold lg:not-sr-only">
              Societas
            </span>
          </Link>
        </div>

        <ul className="flex flex-1 flex-col gap-1">
          {SECTIONS.map((s) => (
            <li key={s.to}>
              <NavLink to={s.to} className={itemClass}>
                <span className="flex w-4 shrink-0 justify-center">
                  <s.Icon size={16} aria-hidden="true" />
                </span>
                <span className={LABEL}>{s.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-border pt-2">
        {/* 240px only: the reading's label text does not fit the 64px rail. */}
        <div className="hidden px-4 pb-2 lg:block">
          <HealthDot />
        </div>
        <div className="flex items-center gap-2 px-3 py-2">
          <span
            aria-hidden="true"
            className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-soft font-titling text-micro font-medium text-accent"
          >
            {initials}
          </span>
          <span className={`${LABEL} text-label text-ink-2`}>Account</span>
        </div>
      </div>
    </div>
  )
}
