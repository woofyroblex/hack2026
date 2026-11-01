import { useEffect, useState } from 'react'
import { RefreshCw, Search } from 'lucide-react'
import { apiClient } from '../../api/client.ts'
import { formatApiError } from '../../api/auth.ts'
import { buttonClass, dateLabel, Empty, ErrorNotice, inputClass, Loading, money, PageTitle, Pagination } from '../shared/WorkspaceUI.tsx'

type PaymentRecord = {
  id: string
  invoice_id: string
  invoice_number: string
  customer_name: string
  amount: string
  currency: string
  method: string
  payment_date: string
  reference: string
  note: string
}
type PaymentPage = { count: number; results: PaymentRecord[] }

export function PaymentsWorkspace() {
  const [data, setData] = useState<PaymentPage | null>(null)
  const [search, setSearch] = useState('')
  const [method, setMethod] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    const params = new URLSearchParams({ page: String(page), page_size: '25' })
    if (search.trim()) params.set('search', search.trim())
    if (method) params.set('method', method)
    if (from) params.set('date_from', from)
    if (to) params.set('date_to', to)
    const timer = window.setTimeout(() => {
      apiClient.get<PaymentPage>(`/payments/?${params.toString()}`)
        .then(({ data: result }) => { if (active) setData(result) })
        .catch(cause => { if (active) { setData(null); setError(formatApiError(cause).message) } })
        .finally(() => { if (active) setLoading(false) })
    }, search ? 200 : 0)
    return () => { active = false; window.clearTimeout(timer) }
  }, [search, method, from, to, page, revision])

  return <div className="space-y-6">
    <PageTitle title="Payments" description="Search recorded receipts and open the invoice each payment settled." action={<button className={buttonClass} aria-label="Refresh payments" onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/>Refresh</button>}/>
    <ErrorNotice message={error} retry={() => setRevision(value => value + 1)}/>
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="grid gap-3 border-b border-slate-200 p-4 sm:grid-cols-2 xl:grid-cols-4">
        <label className="relative sm:col-span-2"><span className="sr-only">Search payments</span><Search size={17} className="absolute left-3 top-3 text-slate-400"/><input className={`${inputClass} pl-9`} placeholder="Invoice, customer, or reference" value={search} onChange={event => { setSearch(event.target.value); setPage(1) }}/></label>
        <select aria-label="Payment method" className={inputClass} value={method} onChange={event => { setMethod(event.target.value); setPage(1) }}><option value="">All methods</option>{['bank_transfer', 'cash', 'card', 'upi', 'other'].map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select>
        <div className="grid grid-cols-2 gap-2"><label className="sr-only" htmlFor="payment-date-from">From date</label><input id="payment-date-from" aria-label="From date" type="date" className={inputClass} value={from} onChange={event => { setFrom(event.target.value); setPage(1) }}/><label className="sr-only" htmlFor="payment-date-to">To date</label><input id="payment-date-to" aria-label="To date" type="date" className={inputClass} value={to} onChange={event => { setTo(event.target.value); setPage(1) }}/></div>
      </div>
      {loading ? <Loading label="Loading payments…"/> : data?.results.length ? <div className="overflow-x-auto"><table className="data-table"><thead><tr><th>Date</th><th>Invoice</th><th>Customer</th><th>Method</th><th>Reference</th><th className="text-right">Amount</th></tr></thead><tbody>{data.results.map(payment => <tr key={payment.id}><td>{dateLabel(payment.payment_date)}</td><td className="font-semibold">{payment.invoice_number}</td><td>{payment.customer_name}</td><td className="capitalize">{payment.method.replaceAll('_', ' ')}</td><td>{payment.reference || '—'}</td><td className="text-right font-medium">{money(payment.amount, payment.currency)}</td></tr>)}</tbody></table></div> : !error ? <Empty title="No payments found" description={search || method || from || to ? 'Try changing the filters.' : 'Payments recorded against invoices will appear here.'}/> : null}
      {data && !loading && <Pagination page={page} total={data.count} pageSize={25} onChange={setPage}/>}
    </section>
  </div>
}
