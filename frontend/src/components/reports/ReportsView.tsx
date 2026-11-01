import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, RefreshCw, WalletCards, Users, FileText, CircleDollarSign, Clock3 } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { apiClient } from '../../api/client.ts'
import { formatApiError } from '../../api/auth.ts'
import { AUTH_CONFIG } from '../../config/auth.ts'
import { Empty, ErrorNotice, Loading, PageTitle, Pagination, inputClass, money, dateLabel } from '../shared/WorkspaceUI.tsx'

type Summary = { currency: string; active_subscriptions: number; customers: number; billed: string; collected: string; outstanding: string; overdue: string }
type RevenuePoint = { month: string; billed: string; collected: string }
type OverdueInvoice = { id: string; invoice_number: string; customer_name: string; currency: string; balance: string; due_date: string; days_overdue: number }
type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] }

function monthLabel(value: string) {
  const [year, month] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('en-IN', { month: 'short', year: '2-digit' }).format(new Date(year, month - 1, 1))
}

export function ReportsView() {
  const now = new Date()
  const [dateFrom, setDateFrom] = useState(() => {
    const start = new Date(now.getFullYear(), now.getMonth() - 5, 1)
    return `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`
  })
  const [dateTo, setDateTo] = useState(() => `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [revenue, setRevenue] = useState<RevenuePoint[]>([])
  const [overdue, setOverdue] = useState<Page<OverdueInvoice> | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [overdueLoading, setOverdueLoading] = useState(true)
  const [summaryError, setSummaryError] = useState('')
  const [overdueError, setOverdueError] = useState('')

  const refresh = useCallback(() => setRevision(value => value + 1), [])

  useEffect(() => {
    let active = true
    const params = { currency: 'INR', date_from: dateFrom, date_to: dateTo }
    setSummaryLoading(true)
    setSummary(null)
    setRevenue([])
    setSummaryError('')
    Promise.all([
      apiClient.get<Summary>(`${AUTH_CONFIG.apiPrefix}/reports/summary/`, { params }),
      apiClient.get<{ currency: string; results: RevenuePoint[] }>(`${AUTH_CONFIG.apiPrefix}/reports/revenue/`, { params }),
    ]).then(([summaryResponse, revenueResponse]) => {
      if (!active) return
      setSummary(summaryResponse.data)
      setRevenue(revenueResponse.data.results)
    }).catch(cause => {
      if (!active) return
      setSummary(null)
      setRevenue([])
      setSummaryError(formatApiError(cause).message)
    }).finally(() => { if (active) setSummaryLoading(false) })
    return () => { active = false }
  }, [dateFrom, dateTo, revision])

  useEffect(() => {
    let active = true
    setOverdueLoading(true)
    setOverdue(null)
    setOverdueError('')
    const timer = window.setTimeout(() => {
      apiClient.get<Page<OverdueInvoice>>(`${AUTH_CONFIG.apiPrefix}/reports/overdue/`, {
        // The overdue ledger is a current balance view, so period filters do not apply.
        params: { currency: 'INR', page, page_size: 10, search },
      }).then(({ data }) => {
        if (active) setOverdue(data)
      }).catch(cause => {
        if (active) setOverdueError(formatApiError(cause).message)
      }).finally(() => { if (active) setOverdueLoading(false) })
    }, search ? 180 : 0)
    return () => { active = false; window.clearTimeout(timer) }
  }, [page, search, revision])

  const cards = summary ? [
    { label: 'Active subscriptions', value: summary.active_subscriptions.toLocaleString('en-IN'), icon: WalletCards, note: 'Current state' },
    { label: 'Billed', value: money(summary.billed, summary.currency), icon: FileText, note: 'Tax-exclusive invoices confirmed in period' },
    { label: 'Collected', value: money(summary.collected, summary.currency), icon: CircleDollarSign, note: 'Payments received in selected period' },
    { label: 'Outstanding', value: money(summary.outstanding, summary.currency), icon: Clock3, note: 'Current open balance' },
  ] : []

  return <div className="space-y-6">
    <PageTitle title="Overview" description="Live subscription and billing activity from your workspace." action={<button className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50" onClick={refresh} disabled={summaryLoading || overdueLoading}><RefreshCw size={16} className={summaryLoading || overdueLoading ? 'animate-spin' : ''}/>Refresh</button>} />

    <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-end">
      <label className="text-xs font-semibold text-slate-600">From<input aria-label="Report start date" className={`${inputClass} mt-1.5`} type="date" value={dateFrom} max={dateTo || undefined} onChange={event => { setDateFrom(event.target.value); setPage(1) }}/></label>
      <label className="text-xs font-semibold text-slate-600">To<input aria-label="Report end date" className={`${inputClass} mt-1.5`} type="date" value={dateTo} min={dateFrom || undefined} onChange={event => { setDateTo(event.target.value); setPage(1) }}/></label>
      <p className="pb-2 text-xs text-slate-500">The date range filters billed and collected amounts. Balances reflect today.</p>
    </section>

    <ErrorNotice message={summaryError} retry={refresh}/>
    {summaryLoading && !summary ? <Loading label="Loading live billing data…"/> : null}
    {summary && <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, note }) => <article key={label} className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><span className="text-sm font-medium text-slate-500">{label}</span><span className="rounded-lg bg-indigo-50 p-2 text-indigo-600"><Icon size={18}/></span></div><p className="mt-4 truncate text-2xl font-semibold tracking-tight text-slate-900">{value}</p><p className="mt-1 text-xs text-slate-500">{note}</p></article>)}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(260px,.7fr)]">
        <article className="rounded-xl border border-slate-200 bg-white p-5"><div className="mb-4"><h2 className="font-semibold text-slate-900">Billed and collected</h2><p className="mt-1 text-sm text-slate-500">Tax-exclusive billed sales by invoice confirmation month; receipts by payment date.</p></div>
          {revenue.length ? <div className="h-72 w-full"><ResponsiveContainer width="100%" height="100%"><AreaChart data={revenue.map(item => ({ ...item, month_label: monthLabel(item.month), billed_value: Number(item.billed), collected_value: Number(item.collected) }))} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
            <defs><linearGradient id="billedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4f46e5" stopOpacity={0.2}/><stop offset="100%" stopColor="#4f46e5" stopOpacity={0.01}/></linearGradient><linearGradient id="collectedFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0f766e" stopOpacity={0.16}/><stop offset="100%" stopColor="#0f766e" stopOpacity={0.01}/></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0"/><XAxis dataKey="month_label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: '#64748b' }}/><YAxis tickLine={false} axisLine={false} width={62} tick={{ fontSize: 11, fill: '#64748b' }} tickFormatter={value => new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(value)}/><Tooltip formatter={(value) => money(Number(value), summary.currency)} labelStyle={{ color: '#0f172a' }}/><Legend/><Area type="monotone" dataKey="billed_value" name="Billed" stroke="#4f46e5" fill="url(#billedFill)" strokeWidth={2.5}/><Area type="monotone" dataKey="collected_value" name="Collected" stroke="#0f766e" fill="url(#collectedFill)" strokeWidth={2.5}/>
          </AreaChart></ResponsiveContainer></div> : <Empty title="No billing activity in this period" description="Issued invoices and payments will appear here when available."/>}
        </article>
        <article className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex items-center gap-3"><span className="rounded-lg bg-amber-50 p-2 text-amber-700"><AlertCircle size={18}/></span><div><h2 className="font-semibold text-slate-900">Needs attention</h2><p className="text-sm text-slate-500">Current overdue balance</p></div></div><p className="mt-6 text-3xl font-semibold tracking-tight text-slate-900">{money(summary.overdue, summary.currency)}</p><p className="mt-2 text-sm text-slate-500">{overdueLoading ? 'Checking overdue invoices…' : overdueError ? 'The overdue invoice count is unavailable.' : `Across ${overdue?.count ?? 0} currently overdue invoices, independent of the date range.`}</p><div className="mt-5 flex items-center gap-2 border-t border-slate-100 pt-4 text-sm text-slate-600"><Users size={16}/>{summary.customers.toLocaleString('en-IN')} customers</div></article>
      </section>
    </>}

    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="flex flex-col justify-between gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-center"><div><h2 className="font-semibold text-slate-900">Overdue invoices</h2><p className="mt-1 text-xs text-slate-500">Current balances past their due date, independent of the selected period.</p></div><input aria-label="Search overdue invoices" className={`${inputClass} sm:max-w-xs`} placeholder="Search invoice or customer" value={search} onChange={event => { setSearch(event.target.value); setPage(1) }}/></div>
      <ErrorNotice message={overdueError} retry={refresh}/>
      {overdueLoading && !overdue ? <Loading label="Loading overdue invoices…"/> : overdue?.results.length ? <div className="overflow-x-auto"><table className="data-table"><thead><tr><th>Invoice</th><th>Customer</th><th>Due date</th><th>Overdue</th><th className="text-right">Balance</th></tr></thead><tbody>{overdue.results.map(item => <tr key={item.id}><td className="font-semibold text-slate-900">{item.invoice_number}</td><td>{item.customer_name}</td><td>{dateLabel(item.due_date)}</td><td><span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">{item.days_overdue} days</span></td><td className="text-right font-semibold">{money(item.balance, item.currency)}</td></tr>)}</tbody></table></div> : !overdueError ? <Empty title="No overdue invoices" description={search ? 'Try a different invoice number or customer.' : 'Your issued invoices are up to date.'}/> : null}
      {overdue && <Pagination page={page} total={overdue.count} pageSize={10} onChange={setPage}/>} 
    </section>
  </div>
}
