import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="py-24 text-center">
      <p className="font-titling text-title text-ink">This page isn't on the floor plan.</p>
      <Link to="/" className="mt-4 inline-block text-body text-datum hover:text-datum">
        Back to the chamber
      </Link>
    </div>
  )
}
