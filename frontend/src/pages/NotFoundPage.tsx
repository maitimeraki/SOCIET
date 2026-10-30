import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="py-24 text-center">
      <h1 className="font-ui text-title text-ink">This page isn't on the map.</h1>
      <Link to="/" className="mt-4 inline-block text-body text-accent hover:text-accent">
        Back to the sheet
      </Link>
    </div>
  )
}
