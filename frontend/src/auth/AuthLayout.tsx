import { Link, Outlet } from 'react-router-dom'
import Card from '../components/ui/Card'
import FiledSheet from '../components/ui/FiledSheet'
import { ruleClasses } from '../components/ui/Rule'
import { DESCRIPTOR, THESIS, WORKED_EXAMPLE } from './authCopy'

/* ── the auth surface's frame ─────────────────────────────────────────────────────────────────────
   A layout is structure: the sheet, the hairline between the two columns, the `<Outlet/>` and the
   wordmark. The form's own rules — the `safeNext` security boundary, the validators, the error copy
   and the §7.2 state marks — live in `authRules.ts` and `authForm.tsx`, not here (R38). */

/**
 * §14.2 Authentication — the door. A single intake form on a white sheet (left) and, standing
 * beside it on the page ground, a **real filed decision** (right): the thing the account is for,
 * shown before a character is typed. The two columns are separated by **one hairline** — the rule
 * token, not a second band — so no surface is invented: the page ground says *the page*, the white
 * sheet says *an object you can pick up*, and the rule says *a boundary*.
 *
 * `<main>` landmark, the wordmark in Archivo caps, and **no shell chrome**: a visitor who has not
 * signed in gets no app navigation.
 *
 * It is a layout route: the form itself is the `<Outlet/>` (SignInPage / SignUpPage), so the frame is
 * built once and the two pages differ only in their fields.
 */
export default function AuthLayout() {
  return (
    <main className="min-h-screen bg-bone">
      <div className="mx-auto grid min-h-screen w-full max-w-6xl grid-cols-1 lg:grid-cols-2">
        <div className="flex flex-col px-6 py-10 sm:px-10 lg:px-14">
          <Link
            to="/"
            className="inline-flex min-h-11 items-center gap-2.5 self-start lg:min-h-0 lg:items-baseline"
          >
            <span className="font-ui text-[18px] uppercase leading-none tracking-[0.08em] text-ink">Societas</span>
            <span className="font-mono text-mono uppercase tracking-[0.06em] text-ink-3">
              {DESCRIPTOR}
            </span>
          </Link>
          {/* The form's sheet: the kit's Card — the canvas and one soft shadow, and no rule
              (house style rule 5). It is a sibling of the filed decision below, never a parent:
              two objects standing on the page ground. */}
          <Card pad={24} radius="lg" className="mt-10 w-full max-w-sm">
            <Outlet />
          </Card>
        </div>

        {/* Stacks below the form under `lg` rather than disappearing: the filed decision is how the
            page belongs to the world (§7.2), and §9 keeps the hierarchy while it drops columns.
            The one hairline turns with the layout — vertical between the columns, horizontal across
            the stack — so it is always one rule, and each one is the edge of the thing it separates:
            the column boundary on the aside, the content block's top edge in the phone stack.
            `rules.css` speaks in `@layer components` and the utilities layer follows it, so the
            plain responsive utilities below turn the hairline without a `!` to outrank it. */}
        <aside
          className={`${ruleClasses('left')} px-6 py-12 sm:px-10 lg:flex lg:flex-col lg:justify-center lg:px-14 lg:py-16 max-lg:border-l-0`}
        >
          <div className={`${ruleClasses('top')} lg:border-t-0`}>
            <p className="max-w-[26ch] font-ui text-title text-ink">{THESIS}</p>
            <div className="mt-10">
              <FiledSheet decision={WORKED_EXAMPLE} sample />
            </div>
          </div>
        </aside>
      </div>
    </main>
  )
}
