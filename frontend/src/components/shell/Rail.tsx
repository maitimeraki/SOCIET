import { Link, NavLink } from 'react-router-dom'
import { CheckCircle, House, ListChecks, Plus, SignOut, SquaresFour } from '@phosphor-icons/react'
import { useAuthStore } from '../../auth/authStore'
import { authLogout } from '../../api/rest'
import HealthDot from './HealthDot'
import { buttonClasses } from '../ui/Button'

/**
 * §7.3 The rail — the persistent left column: the wordmark at its head, the new-decision
 * action, the four destinations in the order the work happens, and the account at its foot.
 * 264px on wide screens, 72px of icons below 1024px, a bottom tab bar on a phone.
 */
const ITEMS = [
  { to: '/overview', label: 'Overview', Icon: House },
  { to: '/documents', label: 'Documents', Icon: SquaresFour },
  { to: '/runs', label: 'Runs', Icon: ListChecks },
  { to: '/results', label: 'Verdict', Icon: CheckCircle },
]

// Resting ink-2; hover a sand fill; active an accent-soft fill with a 3px accent left rule.
const ITEM = 'relative flex min-h-11 items-center gap-3 px-3 py-2 font-ui text-body-sm transition-colors duration-state'
const itemClass = ({ isActive }: { isActive: boolean }) =>
  isActive
    ? `${ITEM} bg-accent-soft font-medium text-ink before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:bg-accent`
    : `${ITEM} text-ink-2 hover:bg-sand hover:text-ink`

/** The label is `sr-only` in the collapsed rail, so every item keeps an accessible name at 72px. */
const LABEL = 'sr-only lg:not-sr-only'

export default function Rail() {
  const email = useAuthStore((s) => s.user?.email ?? '')
  const initials = email.split('@')[0].slice(0, 2).toUpperCase()

  return (
    <div className="flex w-[72px] shrink-0 flex-col border-r border-hairline bg-bone lg:w-[264px]">
      <nav aria-label="Sections" className="flex flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-2 px-2 lg:px-4">
          <Link
            to="/"
            className="flex min-h-11 min-w-11 items-center justify-center gap-2 text-ink lg:justify-start"
          >
            {/* §4.2 draws a diamond, not a logo — the glyph is the mark, the wordmark names it. */}
            <span aria-hidden="true" className="font-display text-title leading-none">
              ◆
            </span>
            <span className="sr-only font-ui text-heading font-semibold lg:not-sr-only">Societas</span>
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

      <div className="border-t border-hairline pt-2">
        {/* The connection reading, 264px only — the label does not fit the 72px rail. */}
        <div className="hidden px-4 pb-2 lg:block">
          <HealthDot />
        </div>
        <div className="flex items-center gap-2 px-3 py-2">
          <span
            aria-hidden="true"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft font-ui text-micro font-medium text-accent"
          >
            {initials}
          </span>
          <span className={`${LABEL} text-label text-ink-2`}>Account</span>
        </div>
        {/* §8.11 — the account row carries a real sign-out, never a dead span. */}
        <div className="px-3 pb-3">
          <button
            type="button"
            onClick={() => {
              void authLogout().finally(() => {
                window.location.href = '/auth/signin'
              })
            }}
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-sm font-mono text-mono text-accent underline underline-offset-4 lg:justify-start"
          >
            {/* §7.3 — visible at 72px too, where the label is for screen readers only. */}
            <SignOut size={16} aria-hidden="true" />
            <span className="sr-only lg:not-sr-only">Sign out</span>
          </button>
        </div>
      </div>
    </div>
  )
}
