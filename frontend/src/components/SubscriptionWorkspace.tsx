import React, { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import {
  AlertCircle,
  CalendarDays,
  Check,
  CircleDollarSign,
  Clock3,
  FileText,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import { apiClient } from '../api/client.ts'
import { formatApiError } from '../api/auth.ts'
import { AUTH_CONFIG } from '../config/auth.ts'

const API = AUTH_CONFIG.apiPrefix

type Subscription = {
  id: string
  number: string
  customer_id: number
  customer: string
  plan_id: number
  plan: string
  status: string
  cadence: string
  start_date: string
  expiry_date: string | null
  quote_valid_until: string | null
  payment_term_days: number
  next_billing_date: string | null
  currency: string
  total: string
  lines: Array<{ id: number; product_id: number; variant_id: number | null; product_name: string; variant_name: string; quantity: number; net_amount: string }>
  timeline: Array<{ action: string; from: string | null; to: string; effective_on: string; reason: string }>
  invoices?: Array<{ id: string; period_start: string; period_end: string; status: string; currency: string; total: string; due_date: string | null }>
  allowed_actions: string[]
}

type ApiError = Error & { status?: number }
type CustomerOption = { id: number; name: string; company: string; email: string }
type PlanOption = { id: number; name: string; cadence: string; base_price: string; minimum_quantity: number; availability_start_date: string; availability_end_date: string | null; payment_term_days: number }
type ProductOption = { id: number; name: string; type: string; sales_price: string; variants: Array<{ id: number; label: string; price_adjustment: string }> }
type TemplateOption = { id: number; name: string; plan_id: number; validity_days: number; payment_term_days: number; default_lines: Array<{ product_id: number; variant_id: number | null; quantity: number }> }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    const response = await apiClient.request<T>({
      url: `${API}${path}`,
      method: init.method || 'GET',
      data: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: { 'Content-Type': 'application/json' },
    })
    return response.data
  } catch (cause) {
    const formatted = formatApiError(cause)
    const error = new Error(formatted.message) as ApiError
    if (axios.isAxiosError(cause)) error.status = cause.response?.status
    throw error
  }
}

const actionNames: Record<string, string> = {
  quote: 'Create quotation',
  send: 'Send quotation',
  confirm: 'Confirm quote',
  reopen: 'Reopen draft',
  activate: 'Activate',
  pause: 'Pause',
  resume: 'Resume',
  close: 'Close',
  renew: 'Create renewal',
}

const statusStyles: Record<string, string> = {
  DRAFT: 'bg-slate-100 text-slate-600',
  QUOTATION: 'bg-amber-100 text-amber-800',
  CONFIRMED: 'bg-blue-100 text-blue-800',
  ACTIVE: 'bg-emerald-100 text-emerald-800',
  PAUSED: 'bg-orange-100 text-orange-800',
  EXPIRED: 'bg-slate-200 text-slate-600',
  CLOSED: 'bg-rose-100 text-rose-800',
}

function dateLabel(value: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value}T00:00:00`))
}

export const SubscriptionWorkspace: React.FC<{ portalMode?: boolean }> = ({ portalMode = false }) => {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
  const [selected, setSelected] = useState<Subscription | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Subscription | null>(null)
  const [busyAction, setBusyAction] = useState('')
  const [reason, setReason] = useState('')

  const loadSubscriptions = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (search.trim()) params.set('search', search.trim())
      if (statusFilter) params.set('status', statusFilter)
      const prefix = portalMode ? '/portal/subscriptions/' : '/subscriptions/'
      const result = await request<{ results: Subscription[] }>(`${prefix}?${params.toString()}`)
      setSubscriptions(result.results)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, portalMode])

  useEffect(() => { void loadSubscriptions() }, [loadSubscriptions])

  async function openDetails(item: Subscription) {
    setError('')
    try {
      const prefix = portalMode ? '/portal/subscriptions/' : '/subscriptions/'
      setSelected(await request<Subscription>(`${prefix}${item.id}/`))
    } catch (err) { setError((err as Error).message) }
  }

  async function runAction(action: string) {
    if (!selected) return
    setBusyAction(action)
    setError('')
    setNotice('')
    try {
      const prefix = portalMode ? '/portal/subscriptions/' : '/subscriptions/'
      const updated = await request<Subscription | { status: string; recipient: string }>(`${prefix}${selected.id}/${action}/`, {
        method: 'POST', body: JSON.stringify({ reason }),
      })
      if (action === 'send') {
        const email = updated as { status: string; recipient: string }
        setNotice(email.status === 'sent' ? `Quotation emailed to ${email.recipient}.` : `Quotation queued for ${email.recipient}.`)
      } else {
        setSelected(updated as Subscription)
        setNotice(`${actionNames[action] || action} completed.`)
      }
      setReason('')
      await loadSubscriptions()
    } catch (err) { setError((err as Error).message) }
    finally { setBusyAction('') }
  }

  async function saveSubscription(payload: Record<string, unknown>, existing?: Subscription) {
    setError('')
    try {
      const saved = await request<Subscription>(existing ? `/subscriptions/${existing.id}/` : '/subscriptions/', {
        method: existing ? 'PATCH' : 'POST', body: JSON.stringify(payload),
      })
      setShowCreate(false)
      setEditing(null)
      setSelected(saved)
      setNotice(existing ? `${saved.number} updated.` : `${saved.number} created as a draft.`)
      await loadSubscriptions()
    } catch (err) { setError((err as Error).message); throw err }
  }

  return (
    <div className="text-slate-900">
      <div>
          <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div><p className="text-xs font-bold uppercase tracking-[.18em] text-blue-600">{portalMode ? 'Customer portal' : 'Subscriptions / Overview'}</p><h1 className="mt-2 text-3xl font-black tracking-tight text-[#101828]">{portalMode ? 'Your subscriptions' : 'Manage subscriptions'}</h1><p className="mt-2 text-sm text-slate-500">{portalMode ? 'View your subscriptions and manage the actions available to you.' : 'Quotes, service periods, and billing status in one place.'}</p></div>
            {!portalMode && <button onClick={() => { setError(''); setEditing(null); setShowCreate(true) }} className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#4965F5] px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#3852de]"><Plus size={17} /> New subscription</button>}
          </div>
          {notice && <div role="status" className="mt-5 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><Check size={17} />{notice}<button onClick={() => setNotice('')} className="ml-auto" aria-label="Dismiss"><X size={16} /></button></div>}
          {error && <ErrorBanner message={error} />}
          <div className="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1fr)_390px]">
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div><h2 className="font-bold">Subscription list</h2><p className="mt-1 text-xs text-slate-500">{subscriptions.length} shown on this page</p></div>
                <div className="flex gap-2">
                  <label className="relative flex-1 sm:w-52"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search number or customer" className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-xs outline-none focus:border-blue-400" /></label>
                  <select aria-label="Filter status" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs outline-none"><option value="">All statuses</option>{['DRAFT', 'QUOTATION', 'CONFIRMED', 'ACTIVE', 'PAUSED', 'EXPIRED', 'CLOSED'].map(s => <option key={s}>{s}</option>)}</select>
                  <button onClick={() => void loadSubscriptions()} aria-label="Refresh" className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /></button>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-left text-sm">
                  <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500"><tr><th className="px-4 py-3 font-semibold">Subscription</th><th className="px-4 py-3 font-semibold">Customer</th><th className="px-4 py-3 font-semibold">Plan</th><th className="px-4 py-3 font-semibold">Next billing</th><th className="px-4 py-3 font-semibold">Amount</th><th className="px-4 py-3 font-semibold">Status</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {loading && subscriptions.length === 0 ? <tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500"><LoaderCircle className="mx-auto mb-2 animate-spin" size={20} />Loading subscriptions…</td></tr> : subscriptions.map(item => <tr key={item.id} onClick={() => void openDetails(item)} className={`cursor-pointer transition-colors hover:bg-blue-50/50 ${selected?.id === item.id ? 'bg-blue-50/70' : ''}`}><td className="px-4 py-4"><span className="font-bold text-slate-800">{item.number}</span><span className="mt-1 block text-xs text-slate-500">Started {dateLabel(item.start_date)}</span></td><td className="px-4 py-4 font-medium text-slate-700">{item.customer}</td><td className="px-4 py-4 text-slate-600">{item.plan}<span className="mt-1 block text-xs text-slate-400">{item.cadence.toLowerCase()}</span></td><td className="px-4 py-4 text-slate-600">{dateLabel(item.next_billing_date)}</td><td className="px-4 py-4 font-semibold">{item.currency} {Number(item.total).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td><td className="px-4 py-4"><span className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wide ${statusStyles[item.status] || 'bg-slate-100 text-slate-600'}`}>{item.status}</span></td></tr>)}
                    {!loading && subscriptions.length === 0 && <tr><td colSpan={6} className="px-4 py-14 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-500"><FileText size={21} /></div><p className="mt-3 font-semibold">No subscriptions yet</p><p className="mt-1 text-sm text-slate-500">{portalMode ? 'Your subscriptions will appear here.' : 'Create one to begin the quotation workflow.'}</p>{!portalMode && <button onClick={() => setShowCreate(true)} className="mt-4 text-sm font-semibold text-blue-600 hover:underline">Create first subscription</button>}</td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

            <aside className="min-h-[420px] rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              {selected ? <>
                <div className="flex items-start justify-between"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{selected.number}</p><h2 className="mt-1 text-lg font-bold">{selected.customer}</h2><p className="text-sm text-slate-500">{selected.plan}</p></div><span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${statusStyles[selected.status] || 'bg-slate-100'}`}>{selected.status}</span></div>
                <div className="mt-5 grid grid-cols-2 gap-3"><Metric icon={<CalendarDays size={16} />} label="Start date" value={dateLabel(selected.start_date)} /><Metric icon={<CalendarDays size={16} />} label="Expiry" value={dateLabel(selected.expiry_date)} /><Metric icon={<Clock3 size={16} />} label="Next billing" value={dateLabel(selected.next_billing_date)} /><Metric icon={<FileText size={16} />} label="Quote valid to" value={dateLabel(selected.quote_valid_until)} /><Metric icon={<Users size={16} />} label="Billing cycle" value={selected.cadence.toLowerCase()} /><Metric icon={<CircleDollarSign size={16} />} label="Total" value={`${selected.currency} ${Number(selected.total).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`} /></div>
                {!portalMode && selected.status === 'DRAFT' && <button onClick={() => { setEditing(selected); setShowCreate(true) }} className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">Edit draft</button>}
                {selected.allowed_actions.length > 0 && <div className="mt-5 border-t border-slate-100 pt-4"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Available actions</p>{selected.allowed_actions.includes('close') && <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason required to close" className="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-blue-400" />}<div className="mt-3 flex flex-wrap gap-2">{selected.allowed_actions.map(action => <button key={action} disabled={busyAction === action || (action === 'close' && !reason.trim())} onClick={() => void runAction(action)} className={`rounded-lg px-3 py-2 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${action === 'close' ? 'border border-rose-200 text-rose-700 hover:bg-rose-50' : 'bg-blue-600 text-white hover:bg-blue-700'}`}>{busyAction === action ? 'Saving…' : actionNames[action] || action}</button>)}</div></div>}
                {selected.lines.length > 0 && <div className="mt-5 border-t border-slate-100 pt-4"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Items</p><div className="mt-2 space-y-2">{selected.lines.map(line => <div key={line.id} className="flex justify-between gap-3 text-sm"><span className="text-slate-600">{line.product_name}{line.variant_name ? ` · ${line.variant_name}` : ''} <span className="text-slate-400">×{line.quantity}</span></span><span className="font-medium">{selected.currency} {Number(line.net_amount).toFixed(2)}</span></div>)}</div></div>}
                {selected.invoices && selected.invoices.length > 0 && <div className="mt-5 border-t border-slate-100 pt-4"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Billing history</p>{selected.invoices.map(invoice => <div key={invoice.id} className="mt-3 flex justify-between gap-3 text-xs"><span>Invoice {invoice.id.slice(0, 8).toUpperCase()} · {dateLabel(invoice.period_start)}{invoice.due_date ? ` · due ${dateLabel(invoice.due_date)}` : ''}</span><span className="shrink-0 text-right font-semibold">{invoice.currency} {Number(invoice.total).toFixed(2)} · {invoice.status}</span></div>)}</div>}
                <div className="mt-5 border-t border-slate-100 pt-4"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Timeline</p><div className="mt-3 space-y-3">{selected.timeline.slice().reverse().map((event, index) => <div key={`${event.action}-${event.effective_on}-${index}`} className="flex gap-3 text-xs"><div className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-blue-500 ring-4 ring-blue-50" /><div><p className="font-semibold capitalize text-slate-700">{event.action.replaceAll('_', ' ')}</p><p className="mt-0.5 text-slate-500">{dateLabel(event.effective_on)}{event.to ? ` · ${event.to}` : ''}{event.reason ? ` · ${event.reason}` : ''}</p></div></div>)}</div></div>
              </> : <div className="flex h-full min-h-[380px] flex-col items-center justify-center text-center"><div className="grid h-12 w-12 place-items-center rounded-full bg-blue-50 text-blue-600"><FileText size={21} /></div><p className="mt-3 font-semibold">Subscription details</p><p className="mt-1 max-w-[230px] text-sm leading-6 text-slate-500">Choose a subscription from the list to view its items, timeline, invoices, and next steps.</p></div>}
            </aside>
          </div>
          <p className="mt-5 flex items-center gap-2 text-xs text-slate-400"><ShieldCheck size={14} /> Customer and plan IDs come from the team catalog; staff actions are checked by the API.</p>
      </div>
        {showCreate && !portalMode && <CreateSubscription initial={editing || undefined} onClose={() => { setShowCreate(false); setEditing(null) }} onSave={saveSubscription} />}
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return <div role="alert" className="mt-4 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-xs leading-5 text-rose-800"><AlertCircle size={16} className="mt-0.5 shrink-0" />{message}</div>
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="rounded-lg bg-slate-50 p-3"><div className="flex items-center gap-1.5 text-slate-400">{icon}<span className="text-[10px] font-semibold uppercase tracking-wide">{label}</span></div><p className="mt-2 truncate text-sm font-bold text-slate-700">{value}</p></div>
}

function CreateSubscription({ initial, onClose, onSave }: { initial?: Subscription; onClose: () => void; onSave: (payload: Record<string, unknown>, existing?: Subscription) => Promise<void> }) {
  const [customerId, setCustomerId] = useState(() => initial ? String(initial.customer_id) : '')
  const [planId, setPlanId] = useState(() => initial ? String(initial.plan_id) : '')
  const [templateId, setTemplateId] = useState('')
  const [customers, setCustomers] = useState<CustomerOption[]>([])
  const [plans, setPlans] = useState<PlanOption[]>([])
  const [products, setProducts] = useState<ProductOption[]>([])
  const [templates, setTemplates] = useState<TemplateOption[]>([])
  const [customerSearch, setCustomerSearch] = useState('')
  const [productSearch, setProductSearch] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [startDate, setStartDate] = useState(() => initial?.start_date || localDateToday())
  const [expiryDate, setExpiryDate] = useState(() => initial?.expiry_date || '')
  const [paymentTermDays, setPaymentTermDays] = useState(() => String(initial?.payment_term_days ?? 0))
  const [lines, setLines] = useState(() => initial?.lines.map(line => ({ productId: String(line.product_id), variantId: line.variant_id ? String(line.variant_id) : '', quantity: String(line.quantity) })) || [{ productId: '', variantId: '', quantity: '1' }])
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const selectedPlan = plans.find(plan => String(plan.id) === planId)

  useEffect(() => {
    let active = true
    const pageSize = '?page_size=100'
    Promise.all([
      request<{ results: PlanOption[] }>(`/plans/${pageSize}`),
      request<{ results: ProductOption[] }>(`/products/${pageSize}`),
      request<{ results: TemplateOption[] }>(`/quote-templates/${pageSize}`),
    ]).then(([planPage, productPage, templatePage]) => {
      if (!active) return
      setPlans(planPage.results)
      setProducts(productPage.results)
      setTemplates(templatePage.results)
    }).catch(err => {
      if (active) setFormError((err as Error).message)
    }).finally(() => {
      if (active) setCatalogLoading(false)
    })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (initial) return
    let active = true
    const params = new URLSearchParams({ page_size: '100' })
    if (customerSearch.trim()) params.set('search', customerSearch.trim())
    const timer = window.setTimeout(() => {
      request<{ results: CustomerOption[] }>(`/customers/?${params.toString()}`).then(page => {
        if (active) setCustomers(current => mergeCatalogOptions(current, page.results))
      }).catch(err => {
        if (active) setFormError((err as Error).message)
      })
    }, 200)
    return () => { active = false; window.clearTimeout(timer) }
  }, [customerSearch, initial])

  useEffect(() => {
    let active = true
    const params = new URLSearchParams({ page_size: '100' })
    if (productSearch.trim()) params.set('search', productSearch.trim())
    const timer = window.setTimeout(() => {
      request<{ results: ProductOption[] }>(`/products/?${params.toString()}`).then(page => {
        if (active) setProducts(current => mergeCatalogOptions(current, page.results))
      }).catch(err => {
        if (active) setFormError((err as Error).message)
      })
    }, 200)
    return () => { active = false; window.clearTimeout(timer) }
  }, [productSearch])

  function selectTemplate(id: string) {
    setTemplateId(id)
    const template = templates.find(item => String(item.id) === id)
    if (!template) {
      const plan = plans.find(item => String(item.id) === planId)
      if (plan) setPaymentTermDays(String(plan.payment_term_days))
      return
    }
    setPlanId(String(template.plan_id))
    setPaymentTermDays(String(template.payment_term_days))
    const templatePlan = plans.find(plan => plan.id === template.plan_id)
    if (templatePlan && startDate < templatePlan.availability_start_date) setStartDate(templatePlan.availability_start_date)
    setLines(template.default_lines.length
      ? template.default_lines.map(line => ({ productId: String(line.product_id), variantId: line.variant_id ? String(line.variant_id) : '', quantity: String(line.quantity) }))
      : [{ productId: '', variantId: '', quantity: '1' }])
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setFormError('')
    const payload: Record<string, unknown> = {
      start_date: startDate,
      expiry_date: expiryDate || null,
      payment_term_days: Number(paymentTermDays),
      lines: lines.map(line => ({ product_id: Number(line.productId), variant_id: line.variantId ? Number(line.variantId) : null, quantity: Number(line.quantity) })),
    }
    if (!initial) {
      payload.customer_id = Number(customerId)
      if (templateId) payload.template_id = Number(templateId)
      else payload.plan_id = Number(planId)
    }
    try { await onSave(payload, initial) }
    catch (err) { setFormError((err as Error).message) }
    finally { setSaving(false) }
  }

  return <div role="dialog" aria-modal="true" aria-labelledby="create-title" className="fixed inset-0 z-40 grid place-items-center overflow-y-auto bg-slate-950/45 p-4 backdrop-blur-sm">
    <form onSubmit={submit} className="my-8 w-full max-w-2xl rounded-2xl bg-white shadow-2xl">
      <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5"><div><p className="text-xs font-bold uppercase tracking-wide text-blue-600">{initial ? 'Draft' : 'New record'}</p><h2 id="create-title" className="mt-1 text-xl font-bold">{initial ? `Edit ${initial.number}` : 'Create subscription'}</h2><p className="mt-1 text-sm text-slate-500">{initial ? 'Update dates, billing term, or product lines.' : 'The server fetches prices and creates a draft.'}</p></div><button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100" aria-label="Close"><X size={19} /></button></div>
      <div className="grid gap-4 px-6 py-5 sm:grid-cols-2">
        {catalogLoading && <div className="sm:col-span-2 text-sm text-slate-500">Loading customers and catalog…</div>}
        {!initial && <><Field label="Find customer"><input value={customerSearch} onChange={e => setCustomerSearch(e.target.value)} placeholder="Search name, company, or email" className={inputClass} /></Field><Field label="Customer"><select required value={customerId} onChange={e => setCustomerId(e.target.value)} className={inputClass}><option value="">Choose a customer</option>{customers.map(customer => <option key={customer.id} value={customer.id}>{customer.company ? `${customer.company} · ` : ''}{customer.name} ({customer.email})</option>)}</select></Field>
        <Field label="Plan"><select value={planId} onChange={e => { const value = e.target.value; const plan = plans.find(item => String(item.id) === value); setPlanId(value); setTemplateId(''); if (plan) { setPaymentTermDays(String(plan.payment_term_days)); if (startDate < plan.availability_start_date) setStartDate(plan.availability_start_date) } }} className={inputClass} required={!templateId} disabled={Boolean(templateId)}><option value="">Choose a plan</option>{plans.map(plan => <option key={plan.id} value={plan.id}>{plan.name} · {plan.cadence} · INR {plan.base_price}</option>)}</select></Field>
        <Field label="Quotation template (optional)"><select value={templateId} onChange={e => selectTemplate(e.target.value)} className={inputClass}><option value="">No template</option>{templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}</select></Field></>}
        <Field label="Start date"><input required type="date" min={selectedPlan?.availability_start_date} max={selectedPlan?.availability_end_date || undefined} value={startDate} onChange={e => setStartDate(e.target.value)} className={inputClass} /></Field>
        <Field label="Expiry date (optional)"><input type="date" value={expiryDate} onChange={e => setExpiryDate(e.target.value)} className={inputClass} /></Field>
        <Field label="Payment term (days)"><input min="0" type="number" value={paymentTermDays} onChange={e => setPaymentTermDays(e.target.value)} className={inputClass} /></Field>
        <div className="sm:col-span-2"><div className="mb-2 flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Quotation items</p><button type="button" onClick={() => setLines(current => [...current, { productId: '', variantId: '', quantity: '1' }])} className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800"><Plus size={14} /> Add item</button></div><Field label="Find product"><input value={productSearch} onChange={e => setProductSearch(e.target.value)} placeholder="Search products" className={inputClass} /></Field><div className="mt-3 space-y-3">{lines.map((line, index) => { const product = products.find(item => String(item.id) === line.productId); return <div key={index} className="grid items-end gap-3 rounded-lg border border-slate-100 bg-slate-50/60 p-3 sm:grid-cols-[1fr_1fr_.7fr_auto]"><Field label="Product"><select required value={line.productId} onChange={e => setLines(current => current.map((item, i) => i === index ? { ...item, productId: e.target.value, variantId: '' } : item))} className={inputClass}><option value="">Choose a product</option>{products.map(item => <option key={item.id} value={item.id}>{item.name} · INR {item.sales_price}</option>)}</select></Field><Field label="Variant"><select value={line.variantId} onChange={e => setLines(current => current.map((item, i) => i === index ? { ...item, variantId: e.target.value } : item))} disabled={!product?.variants.length} className={inputClass}><option value="">No variant</option>{product?.variants.map(variant => <option key={variant.id} value={variant.id}>{variant.label} ({Number(variant.price_adjustment) >= 0 ? '+' : ''}INR {variant.price_adjustment})</option>)}</select></Field><Field label="Quantity"><input required min="1" type="number" value={line.quantity} onChange={e => setLines(current => current.map((item, i) => i === index ? { ...item, quantity: e.target.value } : item))} className={inputClass} /></Field>{lines.length > 1 ? <button type="button" aria-label={`Remove item ${index + 1}`} onClick={() => setLines(current => current.filter((_, i) => i !== index))} className="mb-0.5 rounded-lg border border-slate-200 p-2.5 text-slate-500 hover:bg-white hover:text-rose-600"><Trash2 size={16} /></button> : <span />}</div>})}</div><p className="mt-2 text-[11px] text-slate-400">The server calculates amounts from the current catalog prices and tax rules.</p></div>
        {formError && <div className="sm:col-span-2"><ErrorBanner message={formError} /></div>}
      </div>
      <div className="flex justify-end gap-2 border-t border-slate-100 px-6 py-4"><button type="button" onClick={onClose} className="rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-100">Cancel</button><button disabled={saving || catalogLoading} className="inline-flex items-center gap-2 rounded-lg bg-[#4965F5] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#3852de] disabled:opacity-60">{saving ? <LoaderCircle className="animate-spin" size={16} /> : initial ? <Check size={16} /> : <Plus size={16} />}{initial ? 'Save changes' : 'Create draft'}</button></div>
    </form>
  </div>
}

const inputClass = 'mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-50 disabled:bg-slate-50'

function localDateToday() {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block text-xs font-semibold text-slate-600">{label}{children}</label>
}

function mergeCatalogOptions<T extends { id: number }>(current: T[], incoming: T[]) {
  const byId = new Map(current.map(item => [item.id, item]))
  incoming.forEach(item => byId.set(item.id, item))
  return Array.from(byId.values())
}
