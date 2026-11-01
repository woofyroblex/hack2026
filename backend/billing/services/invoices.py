"""Idempotent invoice generation around the shared pricing engine."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction

from django.utils.module_loading import import_string

from billing.models import Invoice, InvoiceLine, InvoiceNumberSequence, InvoiceStatus
from subscriptions.models import Subscription, SubscriptionEvent


class InvoiceGenerationError(Exception):
    """Base class for invoice generation failures."""


class SubscriptionNotFound(InvoiceGenerationError):
    """The requested subscription does not exist."""


class SubscriptionNotBillable(InvoiceGenerationError):
    """The subscription is not eligible for a new invoice."""


class InvoicePricingNotConfigured(InvoiceGenerationError):
    """No adapter to the authoritative pricing engine has been configured."""


class InvalidPricingResult(InvoiceGenerationError):
    """The pricing engine returned data that cannot be snapshotted safely."""


class InvoicePeriodConflict(InvoiceGenerationError):
    """An invoice already exists for this subscription and period start with a different end."""


def _load_provider():
    dotted_path = getattr(settings, "BILLING_PERIOD_PRICING_PROVIDER", "")
    if not dotted_path:
        raise InvoicePricingNotConfigured(
            "Configure BILLING_PERIOD_PRICING_PROVIDER to the adapter for the authoritative calculate_price service."
        )
    try:
        return import_string(dotted_path)
    except (ImportError, AttributeError, ValueError) as exc:
        raise InvoicePricingNotConfigured(
            f"BILLING_PERIOD_PRICING_PROVIDER could not be loaded: {dotted_path!r}."
        ) from exc


def _decimal(value, field_name):
    if isinstance(value, float):
        raise InvalidPricingResult(f"Pricing value {field_name} must not be a float.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidPricingResult(f"Pricing value {field_name} is not a decimal.") from exc
    if not result.is_finite():
        raise InvalidPricingResult(f"Pricing value {field_name} must be finite.")
    return result


def _source_id(value):
    if not value:
        return ""
    return str(value)[:64]


def _json_snapshot(value):
    """Convert service metadata to JSON-safe primitives without storing floats."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_snapshot(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise InvalidPricingResult("Pricing snapshots must not contain floats.")
    raise InvalidPricingResult(f"Unsupported value in pricing snapshot: {type(value).__name__}.")


def _snapshot_lines(pricing):
    line_data = []
    plan = pricing.get("plan_summary")
    if plan is not None:
        gross = _decimal(plan["base_fee"], "plan_summary.base_fee")
        discount = _decimal(plan.get("discount_amount", 0), "plan_summary.discount_amount")
        taxable = _decimal(plan.get("net_amount", gross - discount), "plan_summary.net_amount")
        tax = _decimal(plan.get("tax_amount", 0), "plan_summary.tax_amount")
        total = _decimal(plan.get("final_total", plan.get("total_amount", taxable + tax)), "plan_summary.final_total")
        line_data.append({
            "description": str(plan.get("name") or plan.get("plan_name") or "Subscription plan")[:255],
            "quantity": Decimal("1"),
            "unit_price": gross,
            "gross_amount": gross,
            "discount_amount": discount,
            "taxable_amount": taxable,
            "tax_rate": _decimal(plan["tax_rate"], "plan_summary.tax_rate") if plan.get("tax_rate") is not None else None,
            "tax_amount": tax,
            "total_amount": total,
            "source_type": "plan",
            "source_id": _source_id(plan.get("plan_id")),
            "product_id_snapshot": "",
            "product_name_snapshot": "",
            "variant_label_snapshot": "",
        })

    for item in pricing.get("lines", []):
        gross = _decimal(item.get("line_subtotal", item.get("gross_amount")), "lines[].line_subtotal")
        discount = _decimal(item.get("discount_amount", 0), "lines[].discount_amount")
        taxable = _decimal(item.get("line_net_amount", item.get("net_amount", gross - discount)), "lines[].line_net_amount")
        tax = _decimal(item.get("tax_amount", 0), "lines[].tax_amount")
        total = _decimal(item.get("final_line_total", item.get("total_amount", taxable + tax)), "lines[].final_line_total")
        product_name = str(item.get("product_name") or "Subscription item")
        variant_label = str(item.get("variant_label") or "").strip()
        description = f"{product_name} / {variant_label}" if variant_label else product_name
        description = description[:255]
        line_data.append({
            "description": description,
            "quantity": _decimal(item.get("quantity", 1), "lines[].quantity"),
            "unit_price": _decimal(item.get("effective_unit_price", item.get("unit_sales_price", 0)), "lines[].effective_unit_price"),
            "gross_amount": gross,
            "discount_amount": discount,
            "taxable_amount": taxable,
            "tax_rate": _decimal(item["tax_rate"], "lines[].tax_rate") if item.get("tax_rate") is not None else None,
            "tax_amount": tax,
            "total_amount": total,
            "source_type": "product",
            "source_id": _source_id(item.get("product_id")),
            "product_id_snapshot": _source_id(item.get("product_id")),
            "product_name_snapshot": str(item.get("product_name") or "")[:255],
            "variant_label_snapshot": str(item.get("variant_label") or "")[:255],
        })

    if not line_data:
        raise InvalidPricingResult("The pricing engine returned no billable lines.")
    for index, line in enumerate(line_data, start=1):
        if line["quantity"] <= 0:
            raise InvalidPricingResult(f"Line {index} quantity must be positive.")
        if any(line[field] < 0 for field in ("unit_price", "gross_amount", "discount_amount", "taxable_amount", "tax_amount", "total_amount")):
            raise InvalidPricingResult(f"Line {index} contains a negative amount.")
        if line["discount_amount"] > line["gross_amount"]:
            raise InvalidPricingResult(f"Line {index} discount exceeds its gross amount.")
        if line["taxable_amount"] != line["gross_amount"] - line["discount_amount"]:
            raise InvalidPricingResult(f"Line {index} taxable amount does not reconcile.")
        if line["total_amount"] != line["taxable_amount"] + line["tax_amount"]:
            raise InvalidPricingResult(f"Line {index} total does not reconcile.")
    return line_data


def _validated_pricing(pricing):
    if not isinstance(pricing, dict):
        raise InvalidPricingResult("The pricing engine must return a dictionary.")
    required = ("currency", "subtotal", "total_discount", "total_tax", "final_total")
    missing = [key for key in required if key not in pricing]
    if missing:
        raise InvalidPricingResult(f"Pricing result is missing: {', '.join(missing)}.")

    currency = str(pricing["currency"]).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise InvalidPricingResult("Pricing result currency must be a three-letter code.")
    if not isinstance(pricing.get("lines", []), list):
        raise InvalidPricingResult("Pricing result lines must be a list.")
    discount_applied = pricing.get("discount_applied")
    try:
        lines = _snapshot_lines(pricing)
    except InvalidPricingResult:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidPricingResult("Pricing result contains an invalid line snapshot.") from exc
    subtotal = _decimal(pricing["subtotal"], "subtotal")
    discount_total = _decimal(pricing["total_discount"], "total_discount")
    tax_total = _decimal(pricing["total_tax"], "total_tax")
    total = _decimal(pricing["final_total"], "final_total")
    if subtotal != sum((line["gross_amount"] for line in lines), Decimal("0")):
        raise InvalidPricingResult("Pricing subtotal does not match the snapshotted line amounts.")
    if discount_total != sum((line["discount_amount"] for line in lines), Decimal("0")):
        raise InvalidPricingResult("Pricing discount total does not match the snapshotted line amounts.")
    if discount_applied is not None:
        applied_saving = _decimal(discount_applied.get("total_saving"), "discount_applied.total_saving")
        if applied_saving != discount_total:
            raise InvalidPricingResult("Applied discount does not match total_discount.")
    if tax_total != sum((line["tax_amount"] for line in lines), Decimal("0")):
        raise InvalidPricingResult("Pricing tax total does not match the snapshotted line amounts.")
    if total != subtotal - discount_total + tax_total:
        raise InvalidPricingResult("Pricing final total does not reconcile with subtotal, discount, and tax.")
    if min(subtotal, discount_total, tax_total, total) < 0 or discount_total > subtotal:
        raise InvalidPricingResult("Pricing totals must be nonnegative and discounts cannot exceed subtotal.")
    return currency, subtotal, discount_total, tax_total, total, lines, discount_applied


def _status_at_period_start(subscription, period_start):
    """Resolve historical eligibility from lifecycle events, not today's status."""
    events = list(SubscriptionEvent.objects.filter(
        subscription=subscription,
        effective_on__lte=period_start,
    ).order_by("effective_on", "created_at", "id"))
    if not events:
        # Older or manually imported subscriptions may not have an event log.
        return subscription.status
    current = Subscription.Status.DRAFT
    for event in events:
        current = event.to_status
    return current


def create_invoice_for_period(subscription_id: UUID, period_start: date, period_end: date) -> Invoice:
    """Create one draft invoice per subscription and half-open billing period."""
    if isinstance(period_start, datetime) or isinstance(period_end, datetime):
        raise ValueError("period_start and period_end must be date values, not datetimes.")
    if not isinstance(period_start, date) or not isinstance(period_end, date) or period_end <= period_start:
        raise ValueError("Billing period must have valid dates with period_end after period_start.")

    lookup = {
        "subscription_id": subscription_id,
        "period_start": period_start,
    }

    def existing_for_period_start():
        existing = Invoice.objects.filter(**lookup).first()
        if existing is not None and existing.period_end != period_end:
            raise InvoicePeriodConflict(
                "An invoice already exists for this subscription and period_start with a different period_end."
            )
        return existing

    try:
        with transaction.atomic():
            try:
                subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
            except Subscription.DoesNotExist as exc:
                raise SubscriptionNotFound(f"Subscription {subscription_id} does not exist.") from exc

            existing = existing_for_period_start()
            if existing is not None:
                if existing.period_end != period_end:
                    raise InvoicePeriodConflict(
                        f"An invoice already exists for {subscription_id} starting {period_start} with a different period end."
                    )
                return existing

            if period_start < subscription.start_date or (
                subscription.expiry_date and period_start > subscription.expiry_date
            ):
                raise SubscriptionNotBillable(f"Subscription {subscription_id} is not billable for this service period.")

            if _status_at_period_start(subscription, period_start) != Subscription.Status.ACTIVE:
                raise SubscriptionNotBillable(f"Subscription {subscription_id} was not active at this service period start.")

            pricing = _load_provider()(subscription, period_start, period_end)
            currency, subtotal, discount_total, tax_total, total, lines, discount_applied = _validated_pricing(pricing)
            sequence_id = InvoiceNumberSequence.objects.create().pk
            customer_snapshot = {}
            if subscription.customer_id is not None:
                customer = subscription.customer
                customer_snapshot = {
                    "customer_id": subscription.customer_id,
                    "name": customer.name,
                    "email": customer.email,
                    "company": customer.company,
                    "phone": customer.phone,
                    "billing_address": customer.billing_address,
                }
            invoice = Invoice.objects.create(
                invoice_number=f"INV-{sequence_id:06d}",
                subscription=subscription,
                period_start=period_start,
                period_end=period_end,
                customer_id_snapshot=subscription.customer_id,
                customer_snapshot=customer_snapshot,
                discount_snapshot=_json_snapshot(discount_applied or {}),
                currency=currency,
                subtotal=subtotal,
                discount_total=discount_total,
                tax_total=tax_total,
                total=total,
                status=InvoiceStatus.DRAFT,
            )
            InvoiceLine.objects.bulk_create([
                InvoiceLine(invoice=invoice, line_number=index, **line)
                for index, line in enumerate(lines, start=1)
            ])
            return invoice
    except IntegrityError as exc:
        # The unique subscription/period-start constraint is the final guard if workers race.
        existing = existing_for_period_start()
        if existing is None:
            raise exc
        return existing
