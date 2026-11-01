import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { FileText, Layers, LogOut, RefreshCw, Save, UserRound, WalletCards } from 'lucide-react'
import { apiClient } from '../../api/client.ts'
import { formatApiError } from '../../api/auth.ts'
import { AUTH_CONFIG } from '../../config/auth.ts'
import { useAuth } from '../../context/useAuth.ts'
import { BrandLogo } from '../BrandLogo.tsx'
import { SubscriptionWorkspace } from '../SubscriptionWorkspace.tsx'
import { InvoiceWorkspace } from '../invoices/InvoiceWorkspace.tsx'
import { ErrorNotice, Loading, money, dateLabel, inputClass } from '../shared/WorkspaceUI.tsx'

type PortalTab = 'overview' | 'subscriptions' | 'invoices' | 'profile'
type PortalSummary = { currency: string; active_subscriptions: number; total_subscriptions: number; issued_invoices: number; outstanding: string; next_billing_date: string | null }
type PortalProfile = { full_name: string; email: string; company: string; phone: string; billing_address: Record<string, string> }
type MeResponse = { full_name?: string; name?: string; email?: string; customer?: { name?: string; company?: string; phone?: string; billing_address?: string | Record<string, string> } }

function addressFields(value?: string | Record<string, string>): Record<string, string> {
  if (typeof value === 'string') return value ? { line1: value } : {}
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === 'string'))
  }
  return {}
}

export function CustomerPortal() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<PortalTab>('overview')
  const [summary, setSummary] = useState<PortalSummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [profile, setProfile] = useState<PortalProfile>({
    full_name: user?.full_name || user?.name || '',
    email: user?.email || '',
    company: '', phone: '', billing_address: {},
  })
  const [profileLoading, setProfileLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let active = true
    setSummaryLoading(true)
    setError('')
    apiClient.get<PortalSummary>(`${AUTH_CONFIG.apiPrefix}/portal/summary/`).then(({ data }) => {
      if (active) setSummary(data)
    }).catch(cause => {
      if (active) setError(formatApiError(cause).message)
    }).finally(() => { if (active) setSummaryLoading(false) })
    return () => { active = false }
  }, [revision])

  useEffect(() => {
    let active = true
    setProfileLoading(true)
    apiClient.get<MeResponse>(AUTH_CONFIG.endpoints.me).then(({ data }) => {
      if (!active) return
      setProfile({
        full_name: data.full_name || data.name || '',
        email: data.email || '',
        company: data.customer?.company || '',
        phone: data.customer?.phone || '',
        billing_address: addressFields(data.customer?.billing_address),
      })
    }).catch(cause => { if (active) setError(formatApiError(cause).message) })
      .finally(() => { if (active) setProfileLoading(false) })
    return () => { active = false }
  }, [])

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const { data } = await apiClient.patch<MeResponse>(AUTH_CONFIG.endpoints.me, {
        full_name: profile.full_name,
        company: profile.company,
        phone: profile.phone,
        billing_address: profile.billing_address,
      })
      setProfile(current => ({
        ...current,
        full_name: data.full_name || data.name || current.full_name,
        company: data.customer?.company || '',
        phone: data.customer?.phone || '',
        billing_address: addressFields(data.customer?.billing_address),
      }))
      setNotice('Your billing profile was updated.')
    } catch (cause) {
      setError(formatApiError(cause).message)
    } finally {
      setSaving(false)
    }
  }

  async function signOut() { await logout() }
  const displayName = profile.full_name || user?.email?.split('@')[0] || 'Your account'
  const navigation: Array<{ id: PortalTab; label: string; icon: typeof WalletCards }> = [
    { id: 'overview', label: 'Overview', icon: WalletCards },
    { id: 'subscriptions', label: 'Subscriptions', icon: Layers },
    { id: 'invoices', label: 'Invoices', icon: FileText },
    { id: 'profile', label: 'Billing profile', icon: UserRound },
  ]

  return <div className="min-h-screen bg-slate-50 text-slate-900">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3 sm:px-6 lg:px-8"><BrandLogo variant="light" size="md" showBadge/><nav aria-label="Customer portal" className="order-3 flex w-full gap-1 overflow-x-auto border-t border-slate-100 pt-2 sm:order-2 sm:ml-4 sm:w-auto sm:flex-1 sm:border-0 sm:pt-0">{navigation.map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => { setTab(id); setNotice(''); setError('') }} aria-current={tab === id ? 'page' : undefined} className={`inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${tab === id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}><Icon size={16}/>{label}</button>)}</nav><div className="ml-auto flex items-center gap-3 sm:order-3"><span className="hidden text-sm font-medium text-slate-600 sm:block">{displayName}</span><button onClick={() => void signOut()} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"><LogOut size={16}/><span className="hidden md:inline">Sign out</span></button></div></div></header>

    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      {tab === 'overview' && <><div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-2xl font-semibold tracking-tight">Welcome, {displayName}</h1><p className="mt-1 text-sm text-slate-500">Your subscriptions, invoices, and billing details in one place.</p></div><button onClick={() => setRevision(value => value + 1)} disabled={summaryLoading} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"><RefreshCw size={16} className={summaryLoading ? 'animate-spin' : ''}/>Refresh</button></div>
        <ErrorNotice message={error} retry={() => setRevision(value => value + 1)}/>
        {summaryLoading && !summary ? <Loading label="Loading your account…"/> : summary && <><section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[
          { label: 'Active subscriptions', value: String(summary.active_subscriptions), note: `${summary.total_subscriptions} total` },
          { label: 'Invoices', value: String(summary.issued_invoices), note: 'Confirmed and paid' },
          { label: 'Outstanding', value: money(summary.outstanding, summary.currency), note: 'Balance due' },
          { label: 'Next billing date', value: summary.next_billing_date ? dateLabel(summary.next_billing_date) : '—', note: 'For active subscriptions' },
        ].map(item => <article key={item.label} className="rounded-xl border border-slate-200 bg-white p-5"><p className="text-sm font-medium text-slate-500">{item.label}</p><p className="mt-4 truncate text-2xl font-semibold tracking-tight">{item.value}</p><p className="mt-1 text-xs text-slate-500">{item.note}</p></article>)}</section>
          <section className="grid gap-4 lg:grid-cols-2"><button onClick={() => setTab('subscriptions')} className="flex items-start gap-4 rounded-xl border border-slate-200 bg-white p-5 text-left hover:border-indigo-300 hover:shadow-sm"><span className="rounded-lg bg-indigo-50 p-3 text-indigo-700"><Layers size={20}/></span><span><span className="block font-semibold">Manage subscriptions</span><span className="mt-1 block text-sm text-slate-500">Review billing dates and available plan actions.</span></span></button><button onClick={() => setTab('invoices')} className="flex items-start gap-4 rounded-xl border border-slate-200 bg-white p-5 text-left hover:border-indigo-300 hover:shadow-sm"><span className="rounded-lg bg-emerald-50 p-3 text-emerald-700"><FileText size={20}/></span><span><span className="block font-semibold">View invoices</span><span className="mt-1 block text-sm text-slate-500">Open billing history and download invoice PDFs.</span></span></button></section></>}
      </>}
      {tab === 'subscriptions' && <SubscriptionWorkspace portalMode/>}
      {tab === 'invoices' && <InvoiceWorkspace portal/>}
      {tab === 'profile' && <section className="max-w-3xl rounded-xl border border-slate-200 bg-white p-5 sm:p-7"><div className="mb-6"><h1 className="text-xl font-semibold">Billing profile</h1><p className="mt-1 text-sm text-slate-500">Keep your contact details current for invoices and account notices.</p></div>{profileLoading ? <Loading label="Loading your profile…"/> : <form className="space-y-5" onSubmit={saveProfile}><ErrorNotice message={error}/>{notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">{notice}</p>}<div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-medium text-slate-700">Full name<input required maxLength={200} className={`${inputClass} mt-1.5`} value={profile.full_name} onChange={event => setProfile(value => ({ ...value, full_name: event.target.value }))}/></label><label className="block text-sm font-medium text-slate-700">Email<input disabled className={`${inputClass} mt-1.5 bg-slate-50`} value={profile.email}/></label><label className="block text-sm font-medium text-slate-700">Company<input maxLength={255} className={`${inputClass} mt-1.5`} value={profile.company} onChange={event => setProfile(value => ({ ...value, company: event.target.value }))}/></label><label className="block text-sm font-medium text-slate-700">Phone<input maxLength={40} className={`${inputClass} mt-1.5`} value={profile.phone} onChange={event => setProfile(value => ({ ...value, phone: event.target.value }))}/></label></div><fieldset className="space-y-4"><legend className="text-sm font-medium text-slate-700">Billing address</legend><label className="block text-sm font-medium text-slate-700">Address<input maxLength={255} className={`${inputClass} mt-1.5`} value={profile.billing_address.line1 || ''} onChange={event => setProfile(value => ({ ...value, billing_address: { ...value.billing_address, line1: event.target.value } }))}/></label><div className="grid gap-4 sm:grid-cols-2">{([['city', 'City'], ['state', 'State or region'], ['postal_code', 'Postal code'], ['country', 'Country']] as const).map(([key, label]) => <label key={key} className="block text-sm font-medium text-slate-700">{label}<input maxLength={100} className={`${inputClass} mt-1.5`} value={profile.billing_address[key] || ''} onChange={event => setProfile(value => ({ ...value, billing_address: { ...value.billing_address, [key]: event.target.value } }))}/></label>)}</div></fieldset><div className="flex justify-end border-t border-slate-100 pt-4"><button disabled={saving} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">{saving ? <RefreshCw size={16} className="animate-spin"/> : <Save size={16}/>}Save billing profile</button></div></form>}</section>}
    </main>
  </div>
}
