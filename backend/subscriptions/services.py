from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Subscription, SubscriptionEvent


class InvalidTransition(ValidationError):
    pass


def add_billing_period(value: date, cadence: str, anchor_day: int | None = None, anchor_month: int | None = None) -> date:
    """Advance by calendar cadence without drifting short-month anchors."""
    cadence = cadence.lower()
    if cadence == 'daily':
        return value + timedelta(days=1)
    if cadence == 'weekly':
        return value + timedelta(days=7)
    if cadence == 'monthly':
        year, month = value.year, value.month + 1
        if month > 12:
            year += 1
            month = 1
        return date(year, month, min(anchor_day or value.day, monthrange(year, month)[1]))
    if cadence == 'yearly':
        year = value.year + 1
        month = anchor_month or value.month
        day = anchor_day or value.day
        return date(year, month, min(day, monthrange(year, month)[1]))
    raise ValidationError({'cadence': 'Unsupported billing cadence.'})


def period_end(subscription: Subscription, start: date) -> date:
    """Return the exclusive end date used by the billing invoice contract."""
    return add_billing_period(start, subscription.cadence, subscription.billing_anchor_day, subscription.billing_anchor_month)


TRANSITIONS = {
    Subscription.Status.DRAFT: {Subscription.Status.QUOTATION},
    Subscription.Status.QUOTATION: {Subscription.Status.CONFIRMED, Subscription.Status.DRAFT},
    Subscription.Status.CONFIRMED: {Subscription.Status.ACTIVE, Subscription.Status.CLOSED},
    Subscription.Status.ACTIVE: {Subscription.Status.PAUSED, Subscription.Status.CLOSED, Subscription.Status.EXPIRED},
    Subscription.Status.PAUSED: {Subscription.Status.ACTIVE, Subscription.Status.CLOSED, Subscription.Status.EXPIRED},
    Subscription.Status.EXPIRED: set(),
    Subscription.Status.CLOSED: set(),
}


def allowed_actions(subscription: Subscription, actor=None) -> list[str]:
    actions = []
    if subscription.status == Subscription.Status.DRAFT:
        actions.append('quote')
    elif subscription.status == Subscription.Status.QUOTATION:
        actions.append('confirm')
        actions.append('send')
    elif subscription.status == Subscription.Status.CONFIRMED:
        actions.append('activate')
    elif subscription.status == Subscription.Status.ACTIVE:
        if subscription.allow_pause_snapshot:
            actions.append('pause')
        if subscription.allow_early_close_snapshot:
            actions.append('close')
        if subscription.allow_renewal_snapshot:
            actions.append('renew')
    elif subscription.status == Subscription.Status.PAUSED:
        actions.append('resume')
        if subscription.allow_early_close_snapshot:
            actions.append('close')
    if actor is not None and not actor.is_staff:
        actions = [a for a in actions if a in {'pause', 'resume', 'close', 'renew'}]
    return actions


@transaction.atomic
def transition(subscription_id, action: str, actor=None, reason: str = '', effective_on: date | None = None) -> Subscription:
    # Lock only the subscription row; nullable related rows cannot be locked by PostgreSQL.
    subscription = Subscription.objects.select_for_update(of=('self',)).select_related('plan').get(pk=subscription_id)
    action = action.lower()
    today = effective_on or timezone.localdate()
    if action not in allowed_actions(subscription, actor):
        raise PermissionDenied('This action is not allowed for the subscription.')

    old_status = subscription.status
    if action == 'quote':
        new_status = Subscription.Status.QUOTATION
        if not subscription.quote_valid_until:
            days = getattr(subscription.template, 'validity_days', 14)
            subscription.quote_valid_until = today + timedelta(days=days)
    elif action == 'confirm':
        if subscription.quote_valid_until and subscription.quote_valid_until < today:
            raise InvalidTransition({'code': 'QUOTE_EXPIRED', 'message': 'This quotation has expired.'})
        new_status = Subscription.Status.CONFIRMED
    elif action == 'activate':
        if subscription.start_date > today:
            subscription.next_billing_date = subscription.start_date
            subscription.save(update_fields=['next_billing_date', 'updated_at'])
            SubscriptionEvent.objects.create(
                subscription=subscription,
                action='activation_scheduled',
                from_status=old_status,
                to_status=Subscription.Status.ACTIVE,
                actor=actor,
                effective_on=subscription.start_date,
            )
            return subscription
        new_status = Subscription.Status.ACTIVE
        subscription.next_billing_date = subscription.start_date
    elif action == 'pause':
        new_status = Subscription.Status.PAUSED
    elif action == 'resume':
        next_date = subscription.next_billing_date or subscription.start_date
        if next_date < today and not subscription.next_billing_date:
            while next_date < today:
                next_date = add_billing_period(next_date, subscription.cadence, subscription.billing_anchor_day, subscription.billing_anchor_month)
        if subscription.expiry_date and next_date > subscription.expiry_date:
            raise InvalidTransition({'code': 'NO_REMAINING_CYCLE', 'message': 'No complete billing cycle remains before expiry.'})
        subscription.next_billing_date = next_date
        new_status = Subscription.Status.ACTIVE
    elif action == 'close':
        if not reason.strip():
            raise ValidationError({'reason': 'A reason is required to close a subscription.'})
        new_status = Subscription.Status.CLOSED
    else:
        raise InvalidTransition({'action': f'Unsupported action: {action}'})

    if new_status != old_status and new_status not in TRANSITIONS[old_status]:
        raise InvalidTransition({'status': f'Cannot move from {old_status} to {new_status}.'})
    subscription.status = new_status
    subscription.save()
    SubscriptionEvent.objects.create(
        subscription=subscription,
        action=action,
        from_status=old_status,
        to_status=new_status,
        actor=actor,
        reason=reason.strip(),
        effective_on=today,
    )
    return subscription


@transaction.atomic
def renew(subscription_id, actor=None) -> Subscription:
    old = Subscription.objects.select_for_update().select_related('plan', 'customer', 'template').prefetch_related('lines__taxes').get(pk=subscription_id)
    if 'renew' not in allowed_actions(old, actor):
        raise PermissionDenied('Renewal is not allowed for this subscription.')
    start = old.expiry_date + timedelta(days=1) if old.expiry_date else (old.next_billing_date or timezone.localdate())
    renewed = Subscription.objects.create(
        customer=old.customer,
        plan=old.plan,
        template=old.template,
        renewal_of=old,
        cadence=old.cadence,
        start_date=start,
        expiry_date=None,
        payment_term_days=old.payment_term_days,
        currency=old.currency,
        base_price_snapshot=old.base_price_snapshot,
        plan_base_price_snapshot=old.plan_base_price_snapshot,
        plan_tax_rate_snapshot=old.plan_tax_rate_snapshot,
        minimum_quantity_snapshot=old.minimum_quantity_snapshot,
        allow_pause_snapshot=old.allow_pause_snapshot,
        allow_early_close_snapshot=old.allow_early_close_snapshot,
        allow_renewal_snapshot=old.allow_renewal_snapshot,
        auto_close_on_expiry_snapshot=old.auto_close_on_expiry_snapshot,
        billing_anchor_day=old.billing_anchor_day or start.day,
        billing_anchor_month=old.billing_anchor_month or start.month,
        created_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )
    for line in old.lines.all():
        tax_ids = list(line.taxes.values_list('pk', flat=True))
        renewed_line = SubscriptionLine.objects.create(
            subscription=renewed,
            product=line.product,
            variant=line.variant,
            quantity=line.quantity,
            product_name_snapshot=line.product_name_snapshot,
            unit_sales_price=line.unit_sales_price,
            variant_adjustment=line.variant_adjustment,
            effective_unit_price=line.effective_unit_price,
            line_subtotal=line.line_subtotal,
            discount_amount=line.discount_amount,
            line_net_amount=line.line_net_amount,
            tax_rate=line.tax_rate,
            tax_amount=line.tax_amount,
            final_line_total=line.final_line_total,
            variant_name_snapshot=line.variant_name_snapshot,
            unit_price=line.unit_price,
            gross_amount=line.gross_amount,
            net_amount=line.net_amount,
            tax_rate_snapshot=line.tax_rate_snapshot,
            sort_order=line.sort_order,
        )
        if tax_ids:
            renewed_line.taxes.set(tax_ids)
    SubscriptionEvent.objects.create(subscription=renewed, action='renewal_draft', to_status=Subscription.Status.DRAFT, actor=actor if getattr(actor, 'is_authenticated', False) else None, reason=f'Renewal of {old.number}', effective_on=start)
    return renewed
