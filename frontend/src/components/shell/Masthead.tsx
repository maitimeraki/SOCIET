import { NavLink, Link } from 'react-router-dom'
import { buttonClasses } from '../ui/Button'
import HealthDot from './HealthDot'

/**
 * The title block's own mark: a triangulation station with the plotted fix inside it. It replaces the
 * incumbent `ChamberMark`, whose arc-of-seats glyph named a room the Survey does not have (addendum §6)
 * — this world's party stands on stations and files a fix.
 *
 * Decorative: the wordmark beside it names the product, so the mark is `aria-hidden`.
 */
function SurveyMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
      <polygon points="9,2.4 16.2,15 1.8,15" fill="none" stroke="var(--color-ink)" strokeWidth="1.4" />
      <circle cx="9" cy="11" r="1.8" fill="var(--color-route)" />
    </svg>
  )
}

const navItem = ({ isActive }: { isActive: boolean }) =>
  `px-2 py-1 font-record text-body transition-colors ${isActive ? 'text-ink underline decoration-datum decoration-2 underline-offset-8' : 'text-ink-2 hover:text-ink'}`

/**
 * §6 Navigation — the title block. A map's title block names the sheet, scales it and states where the
 * reading was taken; this header does the same: the wordmark in Archivo caps, the nav in the record
 * face, the environment reading as a coordinate-style mono tag, and the primary action last.
 *
 * It sits **on** the sheet — opaque and ruled — never floating over the content as a translucent bar.
 */
export default function Masthead() {
  return (
    <header className="flex min-h-14 flex-wrap items-center justify-between gap-y-2 border-b border-ink-4 bg-survey-paper px-6 py-2">
      <div className="flex items-center gap-2.5">
        <SurveyMark />
        <Link to="/" className="font-titling text-[18px] uppercase leading-none tracking-[0.08em] text-ink">
          Societas
        </Link>
      </div>
      <nav aria-label="Primary" className="flex items-center gap-1">
        <NavLink to="/" end className={navItem}>Home</NavLink>
        <NavLink to="/runs" className={navItem}>Runs</NavLink>
        <NavLink to="/agents" className={navItem}>Agents</NavLink>
      </nav>
      <div className="ml-auto flex items-center gap-4">
        <HealthDot />
        <Link to="/new/ingest" className={buttonClasses('primary')}>
          Convene a society
        </Link>
      </div>
    </header>
  )
}
