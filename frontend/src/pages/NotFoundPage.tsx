import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="py-24 text-center">
      <p className="font-serif text-title text-paper">This page isn't on the floor plan.</p>
      <Link to="/" className="mt-4 inline-block text-body text-accent hover:text-accent-strong">
        Back to the chamber
      </Link>
    </div>
  )
}
