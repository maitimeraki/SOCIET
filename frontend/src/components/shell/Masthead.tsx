import { NavLink, Link } from 'react-router-dom'
import HealthDot from './HealthDot'

function ChamberMark() {
  const seats = [-4.5, -3, -1.5, 0, 1.5, 3, 4.5]
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2 13a6 6 0 0 1 12 0" fill="none" stroke="var(--color-accent)" strokeWidth="1.5" />
      {seats.map((x) => (
        <circle key={x} cx={8 + x} cy={13 - Math.sqrt(36 - x * x)} r="0.7" fill="var(--color-paper-faint)" />
      ))}
    </svg>
  )
}

const navItem = ({ isActive }: { isActive: boolean }) =>
  `px-2 py-1 text-body transition-colors ${isActive ? 'text-paper underline decoration-accent decoration-2 underline-offset-8' : 'text-paper-dim hover:text-paper'}`

export default function Masthead() {
  return (
    <header className="flex min-h-14 flex-wrap items-center justify-between gap-y-2 border-b border-ink-700 bg-ink-1000 px-6 py-2">
      <div className="flex items-center gap-2.5">
        <ChamberMark />
        <Link to="/" className="font-serif text-[18px] leading-none text-paper">Simulation World</Link>
      </div>
      <nav aria-label="Primary" className="flex items-center gap-1">
        <NavLink to="/" end className={navItem}>Home</NavLink>
        <NavLink to="/runs" className={navItem}>Runs</NavLink>
        <NavLink to="/agents" className={navItem}>Agents</NavLink>
      </nav>
      <div className="ml-auto flex items-center gap-4">
        <HealthDot />
        <Link to="/new/ingest" className="inline-flex h-10 select-none items-center rounded-[4px] bg-accent px-4 text-body font-medium text-ink-1000 transition-colors hover:bg-accent-strong">
          Convene a society
        </Link>
      </div>
    </header>
  )
}
