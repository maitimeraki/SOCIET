import { Link } from 'react-router-dom'

/**
 * A denied guard renders this page, never a sign-in redirect: the visitor is signed in, they simply
 * don't hold the role the route needs. The server re-checks every request, so this is UX only.
 */
export default function ForbiddenPage() {
  return (
    <div className="py-24 text-center">
      <h1 className="font-ui text-heading text-ink">You don't have access to this page</h1>
      <Link
        to="/overview"
        className="mt-4 inline-flex min-h-11 items-center text-body text-accent hover:text-accent"
      >
        Back to your overview
      </Link>
    </div>
  )
}
