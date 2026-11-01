"""Pure Decimal pricing engine. Inputs are materialized snapshots; this module does no ORM queries."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rest_framework.exceptions import ValidationError

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100.00")


def quantize_currency(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _get(source, key, default=None):
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _decimal(value, field_name):
    if isinstance(value, float):
        raise ValidationError(f"{field_name} must be supplied as Decimal or a decimal string, not float.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a valid decimal amount.") from exc
    if not result.is_finite():
        raise ValidationError(f"{field_name} must be finite.")
    return result


def _tax_rate(taxes, field_name):
    rate = ZERO
    for tax in taxes or ():
        raw = _get(tax, "percentage_rate", tax)
        tax_rate = _decimal(raw, field_name)
        if tax_rate < ZERO or tax_rate > HUNDRED:
            raise ValidationError(f"{field_name} values must be between 0 and 100.")
        rate += tax_rate
    return quantize_currency(rate)


def _allocate_discount(discount_total, eligible_entries):
    if discount_total <= ZERO or not eligible_entries:
        return {}
    eligible_gross = sum((entry["gross"] for entry in eligible_entries), ZERO)
    if eligible_gross <= ZERO:
        return {}

    allocations = {}
    for entry in eligible_entries:
        share = quantize_currency(discount_total * entry["gross"] / eligible_gross)
        allocations[entry["index"]] = min(share, entry["gross"])

    remainder = discount_total - sum(allocations.values(), ZERO)
    remainder_cents = int((remainder / CENT).to_integral_value(rounding=ROUND_HALF_UP))
    ordered = sorted(eligible_entries, key=lambda entry: (-entry["gross"], entry["index"]))
    while remainder_cents:
        changed = False
        step = 1 if remainder_cents > 0 else -1
        for entry in ordered:
            index = entry["index"]
            proposed = allocations[index] + CENT * step
            if ZERO <= proposed <= entry["gross"]:
                allocations[index] = proposed
                remainder_cents -= step
                changed = True
                if remainder_cents == 0:
                    break
        if not changed:
            raise ValidationError("Discount cannot be allocated without making a line negative.")
    return allocations


def calculate_price(plan=None, lines=(), discount_to_apply=None, effective_date=None):
    """Calculate gross, discount, tax and totals using only supplied data and ROUND_HALF_UP."""
    effective_date = effective_date or date.today()
    if isinstance(effective_date, str):
        try:
            effective_date = date.fromisoformat(effective_date)
        except ValueError as exc:
            raise ValidationError("effective_date must be an ISO date.") from exc
    if not isinstance(effective_date, date):
        raise ValidationError("effective_date must be a date.")
    if not isinstance(lines, (list, tuple)):
        raise ValidationError("lines must be a list of chargeable items.")

    plan_entry = None
    plan_summary = None
    if plan is not None:
        base_fee = quantize_currency(_decimal(_get(plan, "base_price", _get(plan, "base_fee", ZERO)), "plan.base_price"))
        if base_fee < ZERO:
            raise ValidationError("Plan base price cannot be negative.")
        plan_tax_rate = _tax_rate(_get(plan, "tax_rates", ()), "plan tax rates")
        plan_entry = {
            "index": -1,
            "kind": "plan",
            "gross": base_fee,
            "tax_rate": plan_tax_rate,
            "source": plan,
        }

    product_entries = []
    # A billable plan itself supplies one unit toward its minimum quantity.
    chargeable_quantity = 1 if plan is not None else 0
    for line_index, line in enumerate(lines):
        product = _get(line, "product")
        if product is None:
            raise ValidationError({"lines": {line_index: "Each line requires a product."}})
        quantity = _get(line, "quantity", 1)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValidationError({"lines": {line_index: "Quantity must be a positive integer."}})

        sales_price = _decimal(_get(product, "sales_price", _get(line, "unit_sales_price", ZERO)), "product.sales_price")
        variant = _get(line, "variant")
        product_id = _get(product, "id", _get(line, "product_id"))
        variant_product_id = _get(variant, "product_id") if variant is not None else None
        if variant_product_id is not None and variant_product_id != product_id:
            raise ValidationError({"lines": {line_index: "Selected variant does not belong to the selected product."}})
        adjustment = _decimal(
            _get(variant, "price_adjustment", _get(line, "variant_adjustment", ZERO)) if variant is not None
            else _get(line, "variant_adjustment", ZERO),
            "variant.price_adjustment",
        )
        effective_unit_price = quantize_currency(sales_price + adjustment)
        if effective_unit_price < ZERO:
            raise ValidationError(
                f"Negative effective price ({effective_unit_price}) is rejected for product {_get(product, 'id')}."
            )
        gross = quantize_currency(effective_unit_price * Decimal(quantity))
        tax_rate = _tax_rate(_get(line, "tax_rates", ()), f"lines[{line_index}].tax_rates")
        product_entries.append({
            "index": line_index,
            "kind": "product",
            "gross": gross,
            "tax_rate": tax_rate,
            "source": line,
            "product": product,
            "variant": variant,
            "quantity": quantity,
            "unit_sales_price": quantize_currency(sales_price),
            "variant_adjustment": quantize_currency(adjustment),
            "effective_unit_price": effective_unit_price,
            "product_id": product_id,
            "variant_id": _get(variant, "id", _get(line, "variant_id")),
            "product_name": _get(product, "name", _get(line, "product_name", "Product")),
            "variant_label": _get(line, "variant_label") or _get(variant, "label", ""),
        })
        chargeable_quantity += quantity

    if plan is None and not product_entries:
        raise ValidationError("At least one product line or a plan is required.")
    minimum_quantity = _get(plan, "minimum_quantity", 1) if plan is not None else 0
    if chargeable_quantity < minimum_quantity:
        raise ValidationError(
            f"Chargeable product quantity ({chargeable_quantity}) is below the plan minimum ({minimum_quantity})."
        )

    entries = ([plan_entry] if plan_entry is not None else []) + product_entries
    subtotal = quantize_currency(sum((entry["gross"] for entry in entries), ZERO))
    discount = None
    discount_total = ZERO
    allocations = {}

    if discount_to_apply is not None:
        discount_type = _get(discount_to_apply, "discount_type", "")
        discount_value = _decimal(
            _get(discount_to_apply, "discount_value", _get(discount_to_apply, "value", ZERO)),
            "discount.discount_value",
        )
        scope = _get(discount_to_apply, "scope", "subscription")
        if discount_value <= ZERO:
            raise ValidationError("Discount value must be greater than zero.")
        if discount_type == "percentage" and discount_value > HUNDRED:
            raise ValidationError("Percentage discounts cannot exceed 100.")
        if discount_type not in ("percentage", "fixed"):
            raise ValidationError("Discount type must be 'percentage' or 'fixed'.")

        applicable_ids = set(_get(discount_to_apply, "applicable_product_ids", ()))
        if scope == "products":
            eligible = [
                entry for entry in product_entries
                if not applicable_ids or entry["product_id"] in applicable_ids
            ]
        elif scope == "plan":
            eligible = [plan_entry] if plan_entry is not None else []
        elif scope == "subscription":
            eligible = entries
        else:
            raise ValidationError("Discount scope must be 'products' or 'subscription'.")

        eligible_gross = sum((entry["gross"] for entry in eligible), ZERO)
        if eligible_gross > ZERO:
            if discount_type == "percentage":
                discount_total = quantize_currency(eligible_gross * discount_value / HUNDRED)
            else:
                discount_total = min(quantize_currency(discount_value), eligible_gross)
            discount_cap = _get(discount_to_apply, "max_discount_cap")
            if discount_cap is not None:
                discount_total = min(discount_total, quantize_currency(_decimal(discount_cap, "discount.max_discount_cap")))
            allocations = _allocate_discount(discount_total, eligible)
            if discount_total > ZERO:
                discount = {
                    "rule_id": _get(discount_to_apply, "id", _get(discount_to_apply, "rule_id")),
                    "name": _get(discount_to_apply, "name", "Discount"),
                    "discount_type": discount_type,
                    "scope": scope,
                    "total_saving": discount_total,
                    "max_discount_cap": discount_cap,
                }

    plan_summary = None
    if plan_entry is not None:
        allocated = allocations.get(plan_entry["index"], ZERO)
        net = plan_entry["gross"] - allocated
        tax_amount = quantize_currency(net * plan_entry["tax_rate"] / HUNDRED)
        plan_summary = {
            "plan_id": _get(plan, "id"),
            "name": _get(plan, "name", "Subscription plan"),
            "billing_cadence": _get(plan, "billing_cadence", "monthly"),
            "base_fee": plan_entry["gross"],
            "discount_amount": allocated,
            "net_amount": net,
            "tax_rate": plan_entry["tax_rate"],
            "tax_amount": tax_amount,
            "final_total": net + tax_amount,
        }

    result_lines = []
    for entry in product_entries:
        allocated = allocations.get(entry["index"], ZERO)
        net = entry["gross"] - allocated
        tax_amount = quantize_currency(net * entry["tax_rate"] / HUNDRED)
        result_lines.append({
            "line_index": entry["index"],
            "product_id": entry["product_id"],
            "product_name": entry["product_name"],
            "variant_id": entry["variant_id"],
            "variant_label": entry["variant_label"],
            "quantity": entry["quantity"],
            "unit_sales_price": entry["unit_sales_price"],
            "variant_adjustment": entry["variant_adjustment"],
            "effective_unit_price": entry["effective_unit_price"],
            "line_subtotal": entry["gross"],
            "discount_amount": allocated,
            "line_net_amount": net,
            "tax_rate": entry["tax_rate"],
            "tax_amount": tax_amount,
            "final_line_total": net + tax_amount,
        })

    total_tax = sum((line["tax_amount"] for line in result_lines), ZERO)
    if plan_summary is not None:
        total_tax += plan_summary["tax_amount"]
    final_total = quantize_currency(subtotal - discount_total + total_tax)
    return {
        "currency": "INR",
        "effective_date": effective_date.isoformat(),
        "plan_summary": plan_summary,
        "lines": result_lines,
        "discount_applied": discount,
        "subtotal": subtotal,
        "total_discount": discount_total,
        "total_tax": quantize_currency(total_tax),
        "final_total": final_total,
    }
