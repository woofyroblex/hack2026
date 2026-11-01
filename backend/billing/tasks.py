"""Asynchronous invoice document rendering."""

from html import escape

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from weasyprint import HTML

from .models import DocumentJob


def _invoice_html(invoice):
    customer = invoice.customer_snapshot or {}
    address = customer.get("billing_address") or {}
    if isinstance(address, dict):
        address_text = ", ".join(str(value) for value in address.values() if value)
    else:
        address_text = str(address)
    customer_name = customer.get("name") or invoice.subscription.customer.name
    lines = []
    for line in invoice.lines.all():
        lines.append(
            "<tr>"
            f"<td>{escape(line.description)}</td>"
            f"<td class='number'>{escape(str(line.quantity))}</td>"
            f"<td class='number'>{escape(invoice.currency)} {line.total_amount:,.2f}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 18mm; }}
body {{ color:#172033; font: 12px Arial, sans-serif; }}
header {{ display:flex; justify-content:space-between; border-bottom:2px solid #243b80; padding-bottom:16px; }}
h1 {{ font-size:26px; margin:0 0 6px; }} h2 {{ font-size:14px; margin:22px 0 8px; }}
.muted {{ color:#667085; }} table {{ width:100%; border-collapse:collapse; margin-top:22px; }}
th,td {{ border-bottom:1px solid #eaecf0; padding:9px 7px; text-align:left; }}
th {{ color:#667085; font-size:10px; text-transform:uppercase; }} .number {{ text-align:right; }}
.totals {{ margin:18px 0 0 auto; width:260px; }} .totals div {{ display:flex; justify-content:space-between; padding:5px 0; }}
.grand {{ border-top:1px solid #98a2b3; font-weight:bold; margin-top:5px; padding-top:10px !important; }}
</style></head><body>
<header><div><h1>Invoice</h1><div class="muted">{escape(invoice.invoice_number)}</div></div>
<div class="number"><strong>{escape(invoice.status)}</strong><br>{escape(str(invoice.currency))}</div></header>
<h2>Bill to</h2><strong>{escape(str(customer_name))}</strong><br>
<span class="muted">{escape(str(customer.get('email') or ''))}<br>{escape(address_text)}</span>
<p class="muted">Billing period: {invoice.period_start.isoformat()} to {invoice.period_end.isoformat()}<br>
Due date: {invoice.due_date.isoformat() if invoice.due_date else '—'}</p>
<table><thead><tr><th>Description</th><th class="number">Quantity</th><th class="number">Amount</th></tr></thead>
<tbody>{''.join(lines)}</tbody></table>
<section class="totals"><div><span>Subtotal</span><span>{invoice.currency} {invoice.subtotal:,.2f}</span></div>
<div><span>Discount</span><span>− {invoice.currency} {invoice.discount_total:,.2f}</span></div>
<div><span>Tax</span><span>{invoice.currency} {invoice.tax_total:,.2f}</span></div>
<div class="grand"><span>Total</span><span>{invoice.currency} {invoice.total:,.2f}</span></div></section>
</body></html>"""


@shared_task(bind=True, max_retries=3, name="billing.render_invoice_pdf")
def render_invoice_pdf(self, job_id):
    with transaction.atomic():
        try:
            job = DocumentJob.objects.select_for_update(of=("self",)).select_related(
                "invoice", "invoice__subscription__customer"
            ).get(pk=job_id)
        except DocumentJob.DoesNotExist:
            return "missing"
        if job.status == DocumentJob.Status.SUCCEEDED:
            return "already_succeeded"
        if job.status == DocumentJob.Status.RUNNING:
            return "already_processing"
        job.status = DocumentJob.Status.RUNNING
        job.attempts += 1
        job.started_at = timezone.now()
        job.last_error = ""
        job.save(update_fields=("status", "attempts", "started_at", "last_error"))
        invoice = job.invoice

    storage_key = f"invoices/{invoice.invoice_number}-{job.pk}.pdf"
    try:
        pdf_bytes = HTML(string=_invoice_html(invoice)).write_pdf()
        if default_storage.exists(storage_key):
            default_storage.delete(storage_key)
        saved_key = default_storage.save(storage_key, ContentFile(pdf_bytes))
    except Exception as exc:
        with transaction.atomic():
            current = DocumentJob.objects.select_for_update().get(pk=job.pk)
            current.status = DocumentJob.Status.FAILED
            current.finished_at = timezone.now()
            current.last_error = f"{type(exc).__name__}: {exc}"[:2000]
            current.save(update_fields=("status", "finished_at", "last_error"))
        raise

    with transaction.atomic():
        current = DocumentJob.objects.select_for_update().get(pk=job.pk)
        current.status = DocumentJob.Status.SUCCEEDED
        current.storage_key = saved_key
        current.finished_at = timezone.now()
        current.last_error = ""
        current.save(update_fields=("status", "storage_key", "finished_at", "last_error"))
    return "succeeded"
