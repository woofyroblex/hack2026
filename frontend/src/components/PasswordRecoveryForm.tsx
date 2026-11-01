import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, CheckCircle2, Loader2, Mail, ShieldCheck } from 'lucide-react'
import { confirmPasswordResetApi, formatApiError, requestPasswordResetApi } from '../api/auth.ts'

type PasswordRecoveryFormProps = {
  uid?: string
  token?: string
  onNavigateToLogin: () => void
}

export function PasswordRecoveryForm({ uid = '', token = '', onNavigateToLogin }: PasswordRecoveryFormProps) {
  const resetMode = Boolean(uid && token)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [complete, setComplete] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (resetMode) {
        if (password.length < 9 || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/[^A-Za-z0-9]/.test(password)) {
          throw new Error('Use at least 9 characters, including lowercase, uppercase, and a special character.')
        }
        if (password !== confirmation) throw new Error('The passwords do not match.')
        await confirmPasswordResetApi({ uid, token, password })
      } else {
        await requestPasswordResetApi(email.trim())
      }
      setComplete(true)
    } catch (cause) {
      setError(formatApiError(cause).message)
    } finally {
      setBusy(false)
    }
  }

  return <section className="w-full max-w-[440px] rounded-2xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/50 sm:p-8">
    <button type="button" onClick={onNavigateToLogin} className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900">
      <ArrowLeft size={16}/>Back to sign in
    </button>
    <div className="mb-6">
      <span className="mb-4 inline-grid h-11 w-11 place-items-center rounded-xl bg-indigo-50 text-indigo-700"><ShieldCheck size={21}/></span>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{resetMode ? 'Choose a new password' : 'Reset your password'}</h1>
      <p className="mt-2 text-sm leading-6 text-slate-500">{resetMode ? 'Use a strong password you have not used for this account before.' : 'Enter your account email. If it matches an account, we will send a reset link.'}</p>
    </div>

    {complete ? <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
      <div className="flex items-start gap-3"><CheckCircle2 size={19} className="mt-0.5 shrink-0 text-emerald-700"/><p>{resetMode ? 'Your password has been updated. Sign in with the new password.' : 'If an account exists for that email, a reset link will be sent.'}</p></div>
      <button type="button" onClick={onNavigateToLogin} className="mt-4 w-full rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800">Return to sign in</button>
    </div> : <form onSubmit={submit} className="space-y-4">
      {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800">{error}</p>}
      {resetMode ? <>
        <label className="block text-sm font-medium text-slate-700">New password<input required autoComplete="new-password" type="password" minLength={9} maxLength={128} value={password} onChange={event => setPassword(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"/></label>
        <label className="block text-sm font-medium text-slate-700">Confirm new password<input required autoComplete="new-password" type="password" minLength={9} maxLength={128} value={confirmation} onChange={event => setConfirmation(event.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100"/></label>
      </> : <label className="block text-sm font-medium text-slate-700">Account email<span className="relative mt-1.5 block"><Mail size={16} className="absolute left-3 top-3 text-slate-400"/><input required autoComplete="email" type="email" maxLength={254} value={email} onChange={event => setEmail(event.target.value)} className="w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" placeholder="name@company.com"/></span></label>}
      <button type="submit" disabled={busy} className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-60">
        {busy && <Loader2 size={16} className="animate-spin"/>}{busy ? 'Please wait…' : resetMode ? 'Update password' : 'Send reset link'}
      </button>
    </form>}
  </section>
}
