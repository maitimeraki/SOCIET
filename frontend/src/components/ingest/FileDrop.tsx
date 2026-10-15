import { useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { UploadSimple } from '@phosphor-icons/react'

const ACCEPT = '.pdf,.docx,.md,.markdown,.txt'

export default function FileDrop({ onFiles, disabled = false }: { onFiles: (files: File[]) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handleDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (disabled) return
    const files = Array.from(event.dataTransfer.files)
    if (files.length > 0) onFiles(files)
  }

  return (
    <label
      onDragOver={(event) => {
        event.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`flex cursor-pointer flex-col items-center gap-2 rounded-[6px] border border-dashed px-6 py-10 text-center transition-colors ${
        dragging ? 'border-datum bg-datum-soft' : 'border-ink-4 bg-survey-paper-2 hover:border-ink-4'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
    >
      <UploadSimple size={20} className="text-ink-2" aria-hidden="true" />
      <span className="text-body text-ink">Drop files here, or browse</span>
      <span className="text-micro text-ink-3">PDF, DOCX, MD, TXT · up to 20 MB each</span>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? [])
          if (files.length > 0) onFiles(files)
          event.target.value = ''
        }}
      />
    </label>
  )
}
