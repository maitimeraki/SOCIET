import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="py-24 text-center">
      <h1 className="font-titling text-title text-ink">This page isn't on the floor plan.</h1>
      <Link to="/" className="mt-4 inline-block text-body text-accent hover:text-accent">
        Back to the sheet
      </Link>
    </div>
  )
}
