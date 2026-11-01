"""Bridge subscription ORM records to the pure catalog pricing engine."""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from rest_framework.exceptions import ValidationError

from discounts.models import DiscountRule
from discounts.services import (
    DiscountQuotaExhausted,
    DiscountService,
    DiscountUnavailable,
    invoice_cycle_quote_id,
)
from products.services.catalog_adapter import calculate_price


def _next_cycle_start(
    start: date,
    cadence: str,
    anchor_day: int | None = None,
    anchor_month: int | None = None,
) -> date:
    if cadence == "daily":
        return start + timedelta(days=1)
    if cadence == "weekly":
        return start + timedelta(days=7)
    if cadence == "monthly":
        year = start.year + (1 if start.month == 12 else 0)
        month = 1 if start.month == 12 else start.month + 1
        day = min(anchor_day or start.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    if cadence == "yearly":
        year = start.year + 1
        month = anchor_month or start.month
        day = min(anchor_day or start.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    raise ValidationError(f"Unsupported billing cadence: {cadence}.")


def _active_tax_rates(taxes):
    return [tax.percentage_rate for tax in taxes if tax.is_active]


def _subscription_plan(subscription):
    plan = subscription.plan
    if plan is None:
        return None
    taxes = _active_tax_rates(plan.taxes.all())
    if subscription.plan_tax_rate_snapshot is not None:
        taxes = [subscription.plan_tax_rate_snapshot]
    return {
        "id": plan.pk,
        "name": plan.name,
        "billing_cadence": subscription.cadence,
        "base_price": subscription.plan_base_price_snapshot
        if subscription.plan_base_price_snapshot is not None
        else (
            subscription.base_price_snapshot
            if subscription.base_price_snapshot is not None
            else plan.base_price
        ),
        "minimum_quantity": subscription.minimum_quantity_snapshot,
        "tax_rates": taxes,
    }


def _subscription_lines(subscription):
    result = []
    lines = (
        subscription.lines.select_related("product", "variant")
        .prefetch_related("taxes", "product__taxes")
        .order_by("sort_order", "id")
    )
    for line in lines:
        product = line.product
        variant = line.variant
        unit_sales_price = (
            line.unit_sales_price if line.unit_sales_price is not None else product.sales_price
        )
        variant_adjustment = (
            line.variant_adjustment
            if line.variant_adjustment is not None
            else (variant.price_adjustment if variant else Decimal("0.00"))
        )
        if line.effective_unit_price is not None:
            variant_adjustment = line.effective_unit_price - unit_sales_price

        selected_taxes = list(line.taxes.all())
        if not selected_taxes:
            selected_taxes = list(product.taxes.all())
        tax_rates = _active_tax_rates(selected_taxes)
        if line.tax_rate is not None:
            tax_rates = [line.tax_rate]

        product_dto = {
            "id": product.pk,
            "name": line.product_name_snapshot or product.name,
            "sales_price": unit_sales_price,
        }
        variant_dto = None
        variant_label = ""
        if variant is not None:
            variant_label = line.variant_name_snapshot or f"{variant.attribute_label}: {variant.option_value}"
            variant_dto = {
                "id": variant.pk,
                "label": variant_label,
                "price_adjustment": variant_adjustment,
            }
        result.append({
            "product": product_dto,
            "product_id": product.pk,
            "product_name": product_dto["name"],
            "variant": variant_dto,
            "variant_id": variant.pk if variant else None,
            "variant_label": variant_label,
            "quantity": line.quantity,
            "unit_sales_price": unit_sales_price,
            "variant_adjustment": variant_adjustment,
            "tax_rates": tax_rates,
        })
    return result


def price_subscription_period(subscription, period_start: date, period_end: date) -> dict:
    """Price one complete billing cycle from a subscription's plan and line snapshots."""
    plan = _subscription_plan(subscription)
    if plan is not None:
        expected_end = _next_cycle_start(
            period_start,
            subscription.cadence,
            subscription.billing_anchor_day,
            subscription.billing_anchor_month,
        )
        if period_end != expected_end:
            raise ValidationError(
                f"Partial billing cycles are not supported for {plan['billing_cadence']} plans."
            )
    lines = _subscription_lines(subscription)
    quote_id = invoice_cycle_quote_id(subscription.pk, period_start)
    excluded_rule_ids = set()
    while True:
        pricing = calculate_price(
            plan=plan,
            lines=lines,
            effective_date=period_start,
            exclude_discount_ids=excluded_rule_ids,
        )
        applied = pricing.get("discount_applied")
        rule_id = applied.get("rule_id") if applied else None
        if not rule_id:
            return pricing
        try:
            rule = DiscountRule.objects.get(pk=rule_id)
            DiscountService.reserve(rule, quote_id)
        except (DiscountQuotaExhausted, DiscountUnavailable, DiscountRule.DoesNotExist):
            excluded_rule_ids.add(str(rule_id))
            continue
        return pricing
