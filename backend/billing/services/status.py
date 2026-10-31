"""Validated invoice status transitions."""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from billing.models import Invoice, InvoiceStatus
from discounts.models import DiscountRule
from discounts.services import DiscountError, DiscountService, invoice_cycle_quote_id
from notifications.services import EmailQueueError, queue_email

logger = logging.getLogger(__name__)


class InvalidInvoiceTransition(Exception):
    """Raised when an invoice moves between unsupported states."""


_ALLOWED_TRANSITIONS = {
    InvoiceStatus.DRAFT: {InvoiceStatus.CONFIRMED, InvoiceStatus.CANCELLED},
    InvoiceStatus.CONFIRMED: {InvoiceStatus.PAID, InvoiceStatus.CANCELLED},
    InvoiceStatus.PAID: set(),
    InvoiceStatus.CANCELLED: set(),
}


def _queue_status_notice(invoice, new_status):
    template_by_status = {
        InvoiceStatus.CONFIRMED: "invoice_confirmed",
        InvoiceStatus.PAID: "invoice_paid",
        InvoiceStatus.CANCELLED: "invoice_cancelled",
    }
    template = template_by_status.get(new_status)
    if not template:
        return
    customer = invoice.subscription.customer
    snapshot = invoice.customer_snapshot or {}
    recipient = snapshot.get("email") or (customer.email if customer else "")
    if not recipient:
        return
    context = {
        "invoice_id": invoice.invoice_number,
        "invoice_number": invoice.invoice_number,
        "customer_name": snapshot.get("name") or (customer.name if customer else "Customer"),
        "total": str(invoice.total),
        "currency": invoice.currency,
        "period_start": invoice.period_start.isoformat(),
        "period_end": invoice.period_end.isoformat(),
        "reason": invoice.cancellation_reason,
        "portal_url": f"{getattr(settings, 'FRONTEND_URL', '').rstrip('/')}/#workspace",
    }
    try:
        queue_email(template, recipient, context, f"invoice:{invoice.pk}:{new_status.lower()}")
    except (EmailQueueError, DjangoValidationError, ValueError) as exc:
        logger.warning("Could not queue %s notice for invoice %s: %s", new_status, invoice.pk, exc)


@transaction.atomic
def transition_invoice_status(invoice_id, new_status, *, reason=""):
    try:
        new_status = InvoiceStatus(new_status)
    except ValueError as exc:
        raise InvalidInvoiceTransition(f"Unsupported invoice status: {new_status!r}.") from exc

    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    old_status = invoice.status
    if invoice.status == new_status:
        return invoice
    if new_status not in _ALLOWED_TRANSITIONS[InvoiceStatus(invoice.status)]:
        raise InvalidInvoiceTransition(f"Cannot move invoice from {invoice.status} to {new_status}.")
    if new_status == InvoiceStatus.CONFIRMED and not invoice.lines.exists():
        raise InvalidInvoiceTransition("An invoice needs at least one line before it can be confirmed.")
    if new_status == InvoiceStatus.CONFIRMED:
        totals = invoice.lines.aggregate(
            subtotal=Sum("gross_amount"), discount_total=Sum("discount_amount"),
            tax_total=Sum("tax_amount"), total=Sum("total_amount"),
        )
        if any(totals[field] != getattr(invoice, field) for field in totals):
            raise InvalidInvoiceTransition("Invoice totals must reconcile with its lines before confirmation.")
        if invoice.total != invoice.subtotal - invoice.discount_total + invoice.tax_total:
            raise InvalidInvoiceTransition("Invoice totals do not reconcile.")
        discount_rule_id = invoice.discount_snapshot.get("rule_id") if invoice.discount_snapshot else None
        if discount_rule_id:
            try:
                rule = DiscountRule.objects.get(pk=discount_rule_id)
                DiscountService.consume(
                    rule,
                    invoice_cycle_quote_id(invoice.subscription_id, invoice.period_start),
                    invoice_id=invoice.pk,
                )
            except (DiscountError, DiscountRule.DoesNotExist) as exc:
                raise InvalidInvoiceTransition("The saved discount reservation is no longer available; contact an administrator to resolve this invoice.") from exc
    paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    if new_status == InvoiceStatus.PAID and (paid != invoice.total or not invoice.payments.exists()):
        raise InvalidInvoiceTransition("An invoice can only be marked paid after its balance has been received.")
    if new_status == InvoiceStatus.CANCELLED and paid:
        raise InvalidInvoiceTransition("An invoice with received payments cannot be cancelled.")
    if new_status == InvoiceStatus.CANCELLED:
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 2000:
            raise InvalidInvoiceTransition("A cancellation reason of 1 to 2000 characters is required.")

    now = timezone.now()
    invoice.status = new_status
    fields = ["status", "updated_at"]
    if new_status == InvoiceStatus.CONFIRMED:
        invoice.confirmed_at = now
        fields.append("confirmed_at")
        invoice.due_date = timezone.localdate(now) + timedelta(days=invoice.subscription.payment_term_days)
        fields.append("due_date")
    elif new_status == InvoiceStatus.PAID:
        invoice.paid_at = now
        fields.append("paid_at")
    elif new_status == InvoiceStatus.CANCELLED:
        invoice.cancelled_at = now
        invoice.cancellation_reason = reason.strip()
        fields.extend(["cancelled_at", "cancellation_reason"])
        if old_status == InvoiceStatus.DRAFT and invoice.discount_snapshot and invoice.discount_snapshot.get("rule_id"):
            try:
                rule = DiscountRule.objects.get(pk=invoice.discount_snapshot["rule_id"])
                DiscountService.release(
                    rule,
                    invoice_cycle_quote_id(invoice.subscription_id, invoice.period_start),
                    reason="Invoice cancelled before issue",
                )
            except (DiscountError, DiscountRule.DoesNotExist):
                pass
    invoice.save(update_fields=fields)
    _queue_status_notice(invoice, new_status)
    return invoice
