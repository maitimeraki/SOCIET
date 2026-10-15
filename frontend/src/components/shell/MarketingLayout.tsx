import { Outlet } from 'react-router-dom'

/**
 * The public frame (plan §1): `/` renders WITHOUT the app shell's chrome, so a visitor who has not
 * signed in gets no app navigation.
 *
 * Today it supplies only what `HomePage` already relied on inside `AppShell` — the sheet and a
 * `<main>` landmark. TODO(Task 17): give it the marketing header/footer and swap the HomePage
 * placeholder for `LandingPage`.
 */
export default function MarketingLayout() {
  return (
    <div className="min-h-screen bg-survey-paper font-record text-body text-ink">
      <main id="content" className="mx-auto w-full max-w-[1200px] px-6 pb-24 pt-8">
        <Outlet />
      </main>
    </div>
  )
}
