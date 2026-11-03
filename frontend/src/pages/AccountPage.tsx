import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, accountDelete, accountExport } from '../api/rest'
import { pollJob } from '../api/poll'
import type { JobStatus, Role, User } from '../api/types'
import { useAuthStore } from '../auth/authStore'
import Button from '../components/ui/Button'
import DefinitionList from '../components/ui/DefinitionList'
import ErrorState from '../components/ui/ErrorState'
import Field from '../components/ui/Field'
import Input from '../components/ui/Input'
import { fmtDay, fmtInt } from '../utils/format'

/** The queued export's nested result carries the object key; the URL is minted top-level. */
interface ExportJobResult {
  object_key?: string
}

/** One poll tick → the percent shown and the signed URL the job read minted (top-level). */
// eslint-disable-next-line react-refresh/only-export-components -- exportTick is the tested mapping
export function exportTick(tick: JobStatus<ExportJobResult>): { percent: number; url: string | null } {
  return {
    percent: Math.max(0, Math.min(100, Math.round(tick.progress * 100))),
    url: tick.download_url ?? null,
  }
}

const ROLE_LABEL: Record<Role, string> = {
  user: 'Member',
  support: 'Support',
  admin: 'Admin',
}

const titleCase = (value: string): string =>
  value ? value.charAt(0).toUpperCase() + value.slice(1) : '—'

/** The typed confirmation matches case-insensitively; the server still receives the account email. */
// eslint-disable-next-line react-refresh/only-export-components -- deleteMatches is the tested rule
export function deleteMatches(email: string, typed: string): boolean {
  return typed.trim().toLowerCase() === email.toLowerCase()
}

export interface AccountPageViewProps {
  user: User
  exporting: boolean
  exportProgress: number | null
  exportError: string | null
  onExport: () => void
  confirm: string
  onConfirmChange: (value: string) => void
  deleting: boolean
  deleteError: string | null
  onDelete: () => void
}

export function AccountPageView({
  user,
  exporting,
  exportProgress,
  exportError,
  onExport,
  confirm,
  onConfirmChange,
  deleting,
  deleteError,
  onDelete,
}: AccountPageViewProps) {
  const matches = deleteMatches(user.email, confirm)

  return (
    <div className="space-y-8">
      <header>
        <p className="font-ui text-label uppercase tracking-[0.09em] text-ink-3">Your account</p>
        <h1 className="mt-3 font-display text-display font-medium tracking-[-0.03em] text-ink">
          Account
        </h1>
      </header>

      <DefinitionList
        items={[
          { term: 'Email', value: user.email },
          { term: 'Plan', value: titleCase(user.plan) },
          { term: 'Role', value: ROLE_LABEL[user.role] },
          { term: 'Experts per decision', value: `Up to ${fmtInt(user.entitlements.max_agents)}` },
          { term: 'Passes per decision', value: `Up to ${fmtInt(user.entitlements.max_rounds)}` },
          { term: 'Units remaining', value: fmtInt(user.entitlements.units_remaining) },
          { term: 'Period ends', value: fmtDay(user.entitlements.period_end) },
        ]}
      />

      <section className="border-t border-rule pt-6">
        <h2 className="font-display text-title font-medium tracking-[-0.02em] text-ink">Download my data</h2>
        <p className="mt-2 max-w-[60ch] text-body text-ink-2">
          We'll prepare a copy of everything tied to this account and start the download when it's ready.
        </p>
        {exporting && (
          <p role="status" className="mt-3 font-mono text-mono text-ink-2">
            Preparing your download{exportProgress !== null ? ` — ${exportProgress}%` : '…'}
          </p>
        )}
        {exportError && (
          <div className="mt-3">
            <ErrorState title="Couldn't prepare your download" detail={exportError} onRetry={onExport} />
          </div>
        )}
        <Button
          type="button"
          variant="secondary"
          className="mt-4 min-h-11"
          loading={exporting}
          disabled={exporting}
          onClick={onExport}
        >
          Download my data
        </Button>
      </section>

      <section className="border-t border-rule pt-6">
        <h2 className="font-display text-title font-medium tracking-[-0.02em] text-ink">Delete my account</h2>
        <p className="mt-2 max-w-[60ch] text-body text-ink-2">
          This cannot be undone. Type your email address to confirm.
        </p>
        <div className="mt-4 max-w-sm">
          <Field label="Account email">
            <Input
              id="account-confirm"
              name="confirm"
              type="email"
              autoComplete="off"
              value={confirm}
              onChange={(e) => onConfirmChange(e.target.value)}
              disabled={deleting}
            />
          </Field>
        </div>
        {deleteError && (
          <p role="alert" className="mt-3 text-body text-ink-2">
            {deleteError}
          </p>
        )}
        <Button
          type="button"
          variant="danger"
          className="mt-4 min-h-11"
          loading={deleting}
          disabled={!matches || deleting}
          onClick={onDelete}
        >
          Delete my account
        </Button>
      </section>
    </div>
  )
}

/** `/account` — the account record, the data export, and the typed-email delete. */
export default function AccountPage() {
  const user = useAuthStore((s) => s.user)
  const clear = useAuthStore((s) => s.clear)
  const navigate = useNavigate()
  const [exporting, setExporting] = useState(false)
  const [exportProgress, setExportProgress] = useState<number | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  if (!user) return null // RequireAuth owns the anonymous case.

  const exportData = async () => {
    if (exporting) return
    setExporting(true)
    setExportError(null)
    setExportProgress(null)
    try {
      const { job_id } = await accountExport()
      const job = await pollJob<ExportJobResult>(job_id, (tick) =>
        setExportProgress(exportTick(tick).percent),
      )
      const url = exportTick(job).url
      if (!url || job.status === 'failed' || job.status === 'cancelled') {
        setExportError(job.error ?? "The server couldn't prepare your download. Try again.")
        return
      }
      window.location.assign(url)
    } catch (err) {
      setExportError(err instanceof ApiError ? err.detail : "Couldn't reach the server. Try again.")
    } finally {
      setExporting(false)
    }
  }

  const deleteAccount = async () => {
    if (deleting || !deleteMatches(user.email, confirm)) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await accountDelete(user.email)
      clear()
      navigate('/')
    } catch (err) {
      setDeleteError(
        err instanceof ApiError
          ? err.detail
          : "Couldn't reach the server. Your account was not deleted.",
      )
      setDeleting(false)
    }
  }

  return (
    <AccountPageView
      user={user}
      exporting={exporting}
      exportProgress={exportProgress}
      exportError={exportError}
      onExport={() => void exportData()}
      confirm={confirm}
      onConfirmChange={setConfirm}
      deleting={deleting}
      deleteError={deleteError}
      onDelete={() => void deleteAccount()}
    />
  )
}
