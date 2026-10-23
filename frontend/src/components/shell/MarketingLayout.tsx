import { Outlet } from 'react-router-dom'

/**
 * The public frame (plan §1): `/` renders WITHOUT the app shell's chrome, so a visitor who has not
 * signed in gets no app navigation.
 *
 * It is deliberately bare — the page's own title block and title-block close are part of the
 * document (`marketing/Hero.tsx`), not chrome wrapped around it. The frame supplies the ground and
 * the `<main>` landmark and nothing that would box the sheet in: a max-width container here would
 * make the full-bleed sheet a card, which the Survey refuses.
 */
export default function MarketingLayout() {
  return (
    <div className="min-h-screen bg-ground text-body text-ink">
      <main id="content">
        <Outlet />
      </main>
    </div>
  )
}
