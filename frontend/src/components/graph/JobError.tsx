import ErrorState from '../ui/ErrorState'
import Button from '../ui/Button'

export default function JobError({ error, onRerun }: { error: string; onRerun: () => void }) {
  return (
    <ErrorState
      title="The map build failed"
      detail={`${error}. Your documents are still here — try again.`}
      actions={
        <Button className="w-full sm:w-auto" onClick={onRerun}>Try again</Button>
      }
    />
  )
}
