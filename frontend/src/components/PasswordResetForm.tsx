import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, CheckCircle2, Loader2, LockKeyhole } from 'lucide-react'
import { confirmPasswordResetApi, formatApiError } from '../api/auth.ts'
import { hasRequiredPasswordComposition } from '../utils/password.ts'

export function PasswordResetForm({ uid, token, onNavigateToLogin }: {
  uid: string
  token: string
  onNavigateToLogin: () => void
}) {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [complete, setComplete] = useState(false)
  const hasResetLink = Boolean(uid && token)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (!hasResetLink) {
      setError('This reset link is invalid or expired. Request a new one to continue.')
      return
    }
    if (!hasRequiredPasswordComposition(password)) {
      setError('Use at least 9 characters with an uppercase letter, a lowercase letter, and a special character.')
      return
    }
    if (password !== confirmPassword) {
      setError('The passwords do not match.')
      return
    }

    setBusy(true)
    try {
      await confirmPasswordResetApi({ uid, token, password })
      window.history.replaceState(null, '', '#reset-password-complete')
      setComplete(true)
    } catch (cause) {
      setError(formatApiError(cause).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="w-full max-w-[440px] rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/50 sm:p-8">
      {complete ? (
        <div className="text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-50 text-emerald-700"><CheckCircle2 size={24} /></span>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">Password updated</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">Sign in with your new password to return to your workspace.</p>
          <button type="button" onClick={onNavigateToLogin} className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white hover:bg-indigo-700">
            <ArrowLeft size={16} /> Back to sign in
          </button>
        </div>
      ) : (
        <>
          <div className="mb-6">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-indigo-50 text-indigo-700"><LockKeyhole size={21} /></span>
            <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">Choose a new password</h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">Set a new password to secure your account.</p>
          </div>

          {error && <p role="alert" className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800">{error}</p>}
          {!hasResetLink && <p role="alert" className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">This reset link is missing information. Request a new link to continue.</p>}

          <form onSubmit={event => void submit(event)} className="space-y-4">
            <label className="block text-sm font-medium text-slate-700">
              New password
              <input autoComplete="new-password" type="password" minLength={9} required value={password} onChange={event => setPassword(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Confirm new password
              <input autoComplete="new-password" type="password" minLength={9} required value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" />
            </label>
            <p className="text-xs leading-5 text-slate-500">At least 9 characters, with uppercase and lowercase letters plus a special character.</p>
            <button type="submit" disabled={busy || !hasResetLink} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60">
              {busy ? <><Loader2 size={16} className="animate-spin" /> Updating…</> : 'Update password'}
            </button>
            <button type="button" disabled={busy} onClick={onNavigateToLogin} className="w-full py-2 text-sm font-medium text-slate-600 hover:text-slate-900">Back to sign in</button>
          </form>
        </>
      )}
    </section>
  )
}
