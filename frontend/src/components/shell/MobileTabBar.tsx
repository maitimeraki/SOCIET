import { Link, NavLink } from 'react-router-dom'
import { CheckCircle, House, ListChecks, Plus, SquaresFour } from '@phosphor-icons/react'

const ITEMS = [
  { to: '/overview', label: 'Overview', Icon: House },
  { to: '/documents', label: 'Documents', Icon: SquaresFour },
  { to: '/runs', label: 'Runs', Icon: ListChecks },
  { to: '/results', label: 'Verdict', Icon: CheckCircle },
]

const itemClass = ({ isActive }: { isActive: boolean }) =>
  `flex min-h-11 min-w-11 flex-1 flex-col items-center justify-center gap-0.5 font-ui text-[10px] leading-none ${
    isActive ? 'font-medium text-accent' : 'text-ink-2'
  }`

/**
 * §7.3/§10.2/§12.3 — on a phone the rail becomes a bottom tab bar: the four destinations in the
 * order the work happens, plus the one floating `+`. Never a 64px icon rail. It is chrome, so it
 * never prints.
 */
export default function MobileTabBar() {
  return (
    <>
      <nav
        aria-label="Sections"
        className="fixed inset-x-0 bottom-0 z-40 flex h-16 items-stretch border-t border-rule bg-bone pb-[env(safe-area-inset-bottom)] print:hidden md:hidden"
      >
        {ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} className={itemClass}>
            {({ isActive }) => (
              <>
                <item.Icon size={20} aria-hidden="true" className={isActive ? 'text-accent' : undefined} />
                <span>{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <Link
        to="/new"
        aria-label="New decision"
        className="action-fill fixed bottom-[72px] right-4 z-50 grid h-14 w-14 place-items-center rounded-full shadow-card print:hidden md:hidden"
      >
        <Plus size={22} aria-hidden="true" />
      </Link>
    </>
  )
}
