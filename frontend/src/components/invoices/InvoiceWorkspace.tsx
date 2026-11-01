import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Download, RefreshCw, Search, Send } from 'lucide-react'
import { apiClient } from '../../api/client.ts'
import { formatApiError } from '../../api/auth.ts'
import { fetchInvoicePdf, invoiceEndpoint } from '../../api/invoices.ts'
import type { Invoice, Page } from '../../api/invoices.ts'
import { buttonClass, dateLabel, Empty, ErrorNotice, Field, inputClass, Loading, Modal, money, PageTitle, Pagination, primaryClass, StatusBadge, SuccessNotice, today } from '../shared/WorkspaceUI.tsx'

export function InvoiceWorkspace({ portal = false }: { portal?: boolean }) {
  const [data, setData] = useState<Page<Invoice> | null>(null)
  const [selected, setSelected] = useState<Invoice | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [paymentOpen, setPaymentOpen] = useState(false)
  const [confirmAction, setConfirmAction] = useState<'confirm' | 'cancel' | null>(null)
  const [cancelReason, setCancelReason] = useState('')
  const endpoint = invoiceEndpoint(portal)
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    const timer = window.setTimeout(() => {
      apiClient.get<Page<Invoice>>(endpoint, { params: { page, page_size: 20, search, status } }).then(({ data: result }) => { if (active) setData(result) }).catch(cause => { if (active) { setData(null); setError(formatApiError(cause).message) } }).finally(() => { if (active) setLoading(false) })
    }, search ? 200 : 0)
    return () => { active = false; window.clearTimeout(timer) }
  }, [endpoint, page, search, status, revision])
  useEffect(() => {
    if (!selectedId) { setSelected(null); setDetailLoading(false); return }
    let active = true
    setSelected(null)
    setDetailLoading(true); setError('')
    apiClient.get<Invoice>(`${endpoint}${selectedId}/`).then(({ data: result }) => { if (active) setSelected(result) }).catch(cause => { if (active) { setSelected(null); setError(formatApiError(cause).message) } }).finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [endpoint, selectedId, revision])
  async function act(action: 'confirm' | 'cancel' | 'send', reason = '') {
    if (!selected) return
    setBusy(action); setError(''); setNotice('')
    try {
      const result = await apiClient.post<Invoice | { status: string; recipient: string }>(`${endpoint}${selected.id}/${action}/`, action === 'cancel' ? { reason } : {})
      if (action === 'send') {
        const email = result.data as { status: string; recipient: string }
        setNotice(email.status === 'sent' ? `Invoice email sent to ${email.recipient}.` : `Invoice email queued for ${email.recipient}.`)
      } else {
        setSelected(result.data as Invoice)
        setNotice(action === 'confirm' ? 'Invoice confirmed.' : 'Invoice cancelled.')
        setRevision(value => value + 1)
      }
      setConfirmAction(null)
    } catch (cause) { setError(formatApiError(cause).message); setConfirmAction(null) }
    finally { setBusy('') }
  }
  async function download() {
    if (!selected) return
    setBusy('pdf'); setError(''); setNotice('')
    try {
      const blob = await fetchInvoicePdf(selected.id, portal)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = `${selected.invoice_number}.pdf`
      document.body.append(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice('Invoice PDF downloaded.')
    } catch (cause) { setError(formatApiError(cause).message) }
    finally { setBusy('') }
  }
  const allowed = (action: string) => !portal && selected?.allowed_actions?.includes(action)
  return <div className="space-y-6"><PageTitle title={selectedId ? selected?.invoice_number || 'Invoice details' : portal ? 'Your invoices' : 'Invoices'} description={selectedId ? 'Billing details, documents, and payment history.' : portal ? 'Your billing history and downloadable invoices.' : 'Review invoices, record payments, and follow up on balances.'} action={<button className={buttonClass} aria-label="Refresh invoices" disabled={Boolean(busy)} onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/>Refresh</button>}/><ErrorNotice message={error} retry={() => setRevision(value => value + 1)}/><SuccessNotice message={notice}/>{selectedId ? <><button className={buttonClass} disabled={Boolean(busy)} onClick={() => { setSelectedId(''); setNotice(''); setError('') }}><ArrowLeft size={16}/>All invoices</button>{detailLoading ? <Loading label="Loading invoice…"/> : selected && <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]"><div className="space-y-6"><section className="rounded-xl border border-slate-200 bg-white p-6"><div className="flex items-start justify-between gap-3"><div><h2 className="text-xl font-semibold">{selected.customer_name}</h2><p className="mt-1 text-sm text-slate-500">{selected.invoice_number}</p></div><StatusBadge status={selected.status}/></div><dl className="mt-6 grid gap-4 sm:grid-cols-3"><div><dt className="text-xs text-slate-500">Period start</dt><dd className="mt-1 text-sm">{dateLabel(selected.period_start)}</dd></div><div><dt className="text-xs text-slate-500">Period end (exclusive)</dt><dd className="mt-1 text-sm">{dateLabel(selected.period_end)}</dd></div><div><dt className="text-xs text-slate-500">Due date</dt><dd className="mt-1 text-sm">{dateLabel(selected.due_date)}</dd></div></dl><div className="mt-6 overflow-x-auto"><table className="data-table"><thead><tr><th>Item</th><th className="text-right">Quantity</th><th className="text-right">Amount</th></tr></thead><tbody>{selected.lines.map(line => <tr key={line.id}><td>{line.description}</td><td className="text-right">{line.quantity}</td><td className="text-right">{money(line.total_amount, selected.currency)}</td></tr>)}</tbody></table></div><dl className="ml-auto mt-5 max-w-xs space-y-3 text-sm">{[['Subtotal', selected.subtotal], ['Discount', selected.discount_total], ['Tax', selected.tax_total], ['Total', selected.total]].map(([label, value]) => <div key={label} className={`flex justify-between gap-5 ${label === 'Total' ? 'border-t border-slate-200 pt-3 font-semibold' : 'text-slate-600'}`}><dt>{label}</dt><dd>{label === 'Discount' ? '−' : ''}{money(value, selected.currency)}</dd></div>)}</dl></section><section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><h2 className="border-b border-slate-200 px-6 py-4 font-semibold">Payment history</h2>{selected.payments.length ? <div className="overflow-x-auto"><table className="data-table"><thead><tr><th>Date</th><th>Method</th><th>Reference</th><th className="text-right">Amount</th></tr></thead><tbody>{selected.payments.map(payment => <tr key={payment.id}><td>{dateLabel(payment.payment_date)}</td><td className="capitalize">{payment.method.replaceAll('_', ' ')}</td><td>{payment.reference || '—'}</td><td className="text-right">{money(payment.amount, selected.currency)}</td></tr>)}</tbody></table></div> : <Empty title="No payments recorded" description={portal ? 'Recorded payments will appear here.' : 'Record a received payment after confirming this invoice.'}/>}</section></div><aside className="h-fit space-y-5 rounded-xl border border-slate-200 bg-white p-6"><div><p className="text-sm text-slate-500">Outstanding balance</p><p className="mt-2 text-3xl font-semibold tracking-tight">{money(selected.balance, selected.currency)}</p><p className="mt-2 text-sm text-slate-500">{money(selected.amount_paid, selected.currency)} paid</p></div><div className="space-y-3 border-t border-slate-200 pt-5">{allowed('confirm') && <button className={`${primaryClass} w-full`} disabled={Boolean(busy)} onClick={() => setConfirmAction('confirm')}>Confirm invoice</button>}{allowed('payments') && <button className={`${primaryClass} w-full`} disabled={Boolean(busy)} onClick={() => setPaymentOpen(true)}>Record payment</button>}{(portal || allowed('pdf')) && <button className={`${buttonClass} w-full`} disabled={Boolean(busy)} onClick={() => void download()}><Download size={16}/>{busy === 'pdf' ? 'Preparing PDF…' : 'Download PDF'}</button>}{allowed('send') && <button className={`${buttonClass} w-full`} disabled={Boolean(busy)} onClick={() => void act('send')}><Send size={16}/>{busy === 'send' ? 'Queuing…' : 'Email invoice'}</button>}{allowed('cancel') && <button className="w-full rounded-lg py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50" disabled={Boolean(busy)} onClick={() => { setCancelReason(''); setConfirmAction('cancel') }}>Cancel invoice</button>}</div></aside></div>}</> : <section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="flex flex-col justify-between gap-3 border-b border-slate-200 p-4 sm:flex-row"><label className="relative w-full max-w-sm"><span className="sr-only">Search invoices</span><Search size={18} className="absolute left-3 top-3 text-slate-400"/><input className={`${inputClass} pl-10`} placeholder="Search invoice or customer" value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}/></label><select aria-label="Invoice status" className={`${inputClass} sm:w-44`} value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}><option value="">All statuses</option>{(portal ? ['Confirmed', 'Paid'] : ['Draft', 'Confirmed', 'Paid', 'Cancelled']).map(value => <option key={value}>{value}</option>)}</select></div>{loading ? <Loading label="Loading invoices…"/> : data?.results.length ? <div className="overflow-x-auto"><table className="data-table"><thead><tr><th>Invoice</th>{!portal && <th>Customer</th>}<th>Due date</th><th>Status</th><th className="text-right">Total</th><th className="text-right">Balance</th></tr></thead><tbody>{data.results.map(invoice => <tr key={invoice.id}><td><button onClick={() => { setSelected(null); setSelectedId(invoice.id); setNotice(''); setError('') }} className="font-semibold text-blue-700 hover:underline">{invoice.invoice_number}</button></td>{!portal && <td>{invoice.customer_name}</td>}<td>{dateLabel(invoice.due_date)}</td><td><StatusBadge status={invoice.status}/></td><td className="text-right">{money(invoice.total, invoice.currency)}</td><td className="text-right font-medium">{money(invoice.balance, invoice.currency)}</td></tr>)}</tbody></table></div> : !error ? <Empty title="No invoices found" description={search || status ? 'Try changing your search or status filter.' : portal ? 'Your confirmed invoices will appear here.' : 'Invoices are generated for subscriptions when billing is due.'}/> : null}{data && !loading && <Pagination page={page} total={data.count} onChange={setPage}/>}</section>}{confirmAction && selected && <Modal title={confirmAction === 'confirm' ? 'Confirm invoice' : 'Cancel invoice'} busy={Boolean(busy)} onClose={() => setConfirmAction(null)}><p className="text-sm leading-6 text-slate-600">{confirmAction === 'confirm' ? `${selected.invoice_number} will become available to the customer and ready for payment.` : `Cancel ${selected.invoice_number}? It will remain in the billing history and cannot accept payments.`}</p>{confirmAction === 'cancel' && <div className="mt-4"><Field label="Reason for cancellation"><textarea autoFocus required maxLength={2000} rows={3} className={inputClass} value={cancelReason} onChange={event => setCancelReason(event.target.value)}/></Field></div>}<div className="mt-6 flex justify-end gap-3"><button className={buttonClass} disabled={Boolean(busy)} onClick={() => setConfirmAction(null)}>Go back</button><button className={primaryClass} disabled={Boolean(busy) || (confirmAction === 'cancel' && !cancelReason.trim())} onClick={() => void act(confirmAction, cancelReason)}>{busy ? 'Saving…' : confirmAction === 'confirm' ? 'Confirm invoice' : 'Cancel invoice'}</button></div></Modal>}{paymentOpen && selected && <PaymentForm invoice={selected} onClose={() => setPaymentOpen(false)} onSaved={invoice => { setSelected(invoice); setPaymentOpen(false); setNotice('Payment recorded.'); setRevision(value => value + 1) }}/>}</div>
}

function PaymentForm({ invoice, onClose, onSaved }: { invoice: Invoice; onClose: () => void; onSaved: (invoice: Invoice) => void }) {
  const [amount, setAmount] = useState(invoice.balance)
  const [method, setMethod] = useState('bank_transfer')
  const [date, setDate] = useState(today())
  const [reference, setReference] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null)
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    const payload = { amount, method, payment_date: date, reference }
    const fingerprint = JSON.stringify(payload)
    if (attempt.current?.fingerprint !== fingerprint) attempt.current = { fingerprint, key: crypto.randomUUID() }
    try {
      const { data } = await apiClient.post<Invoice>(`${invoiceEndpoint()}${invoice.id}/payments/`, payload, { headers: { 'Idempotency-Key': attempt.current.key } })
      onSaved(data)
    } catch (cause) { setError(formatApiError(cause).message) }
    finally { setBusy(false) }
  }
  return <Modal title="Record payment" onClose={onClose} busy={busy}><form className="space-y-5" onSubmit={submit}><p className="text-sm text-slate-500">Record money already received for {invoice.invoice_number}.</p><ErrorNotice message={error}/><Field label={`Amount (${invoice.currency})`}><input autoFocus required type="number" step="0.01" min="0.01" max={invoice.balance} className={inputClass} value={amount} onChange={e => setAmount(e.target.value)}/></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Method"><select className={inputClass} value={method} onChange={e => setMethod(e.target.value)}>{['bank_transfer', 'cash', 'card', 'upi', 'other'].map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></Field><Field label="Payment date"><input required type="date" max={today()} className={inputClass} value={date} onChange={e => setDate(e.target.value)}/></Field></div><Field label="Reference (optional)"><input className={inputClass} maxLength={120} value={reference} onChange={e => setReference(e.target.value)} placeholder="Transaction or receipt reference"/></Field><div className="flex justify-end gap-3 border-t border-slate-200 pt-5"><button type="button" className={buttonClass} disabled={busy} onClick={onClose}>Cancel</button><button className={primaryClass} disabled={busy}>{busy ? 'Saving…' : 'Record payment'}</button></div></form></Modal>
}
