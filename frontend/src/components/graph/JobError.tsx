import ErrorState from '../ui/ErrorState'
import Button from '../ui/Button'

export default function JobError({ error, onRerun }: { error: string; onRerun: () => void }) {
  return (
    <ErrorState
      title="The graph build failed"
      detail={`${error}. Your documents are still here — try again.`}
      actions={
        <Button onClick={onRerun}>Run again</Button>
      }
    />
  )
}
