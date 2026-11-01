import axios from 'axios'
import { apiClient } from './client.ts'
import { AUTH_CONFIG } from '../config/auth.ts'

export interface Invoice {
  id: string
  invoice_number: string
  subscription_id: string
  customer_name: string
  status: 'Draft' | 'Confirmed' | 'Paid' | 'Cancelled'
  currency: string
  subtotal: string
  discount_total: string
  tax_total: string
  total: string
  amount_paid: string
  balance: string
  period_start: string
  period_end: string
  due_date: string | null
  cancellation_reason?: string
  allowed_actions: string[]
  lines: Array<{ id: string; description: string; quantity: string | number; unit_price: string; total_amount: string }>
  payments: Array<{ id: string; amount: string; method: string; payment_date: string; reference: string }>
}
export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
export const invoiceEndpoint = (portal = false) => `${AUTH_CONFIG.apiPrefix}/${portal ? 'portal/' : ''}invoices/`

/** A 202 response contains a job, never a downloadable PDF. */
export async function fetchInvoicePdf(id: string, portal = false, options: { attempts?: number; wait?: () => Promise<void> } = {}): Promise<Blob> {
  const endpoint = `${invoiceEndpoint(portal)}${id}/pdf/`
  // Both staff and customer PDF requests create or retry the durable document job.
  await apiClient.post(endpoint, {})
  const wait = options.wait || (() => new Promise<void>(resolve => window.setTimeout(resolve, 1500)))
  for (let attempt = 0; attempt < (options.attempts ?? 30); attempt++) {
    try {
      const response = await apiClient.get<Blob>(endpoint, { responseType: 'blob' })
      if (response.status === 200 && response.data.type.includes('pdf')) return response.data
      const job = await readDocumentJob(response.data)
      if (!job) throw new Error('The document service returned an unexpected response.')
      if (job.status?.toLowerCase() === 'failed') throw new Error(job.message || 'PDF generation failed. Please try again.')
    } catch (cause) {
      if (cause instanceof Error && !axios.isAxiosError(cause)) throw cause
      if (axios.isAxiosError(cause)) {
        const job = await readDocumentJob(cause.response?.data)
        if (job?.status?.toLowerCase() === 'failed') throw new Error(job.message || 'PDF generation failed. Please try again.')
        if (job?.message) throw new Error(job.message)
      }
      throw cause
    }
    await wait()
  }
  throw new Error('The PDF is still being prepared. Try downloading again shortly.')
}

async function readDocumentJob(value: unknown): Promise<{ status?: string; message?: string } | null> {
  try {
    const text = value instanceof Blob ? await value.text() : typeof value === 'string' ? value : null
    const parsed = text ? JSON.parse(text) : value
    if (!parsed || typeof parsed !== 'object') return null
    const job = parsed as { status?: unknown; message?: unknown }
    return {
      status: typeof job.status === 'string' ? job.status : undefined,
      message: typeof job.message === 'string' ? job.message : undefined,
    }
  } catch {
    return null
  }
}
