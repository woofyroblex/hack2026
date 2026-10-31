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
        if subscription.quote_valid_until and subscription.quote_valid_until < timezone.localdate():
            actions.append('reopen')
        else:
            actions.extend(('confirm', 'send'))
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
    subscription = Subscription.objects.select_for_update().select_related('plan').get(pk=subscription_id)
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
        if subscription.renewal_of_id:
            previous = Subscription.objects.select_for_update().get(pk=subscription.renewal_of_id)
            expected_start = previous.expiry_date + timedelta(days=1) if previous.expiry_date else previous.next_billing_date
            if (
                previous.status != Subscription.Status.ACTIVE
                or expected_start != subscription.start_date
                or expected_start is None
                or expected_start <= today
            ):
                raise InvalidTransition({
                    'code': 'RENEWAL_DATE_CHANGED',
                    'message': 'The original subscription changed after this renewal draft was created. Create a new renewal draft.',
                })
            if previous.expiry_date is None:
                previous.expiry_date = subscription.start_date - timedelta(days=1)
                previous.save(update_fields=['expiry_date', 'updated_at'])
                SubscriptionEvent.objects.create(
                    subscription=previous,
                    action='renewal_scheduled',
                    from_status=previous.status,
                    to_status=previous.status,
                    actor=actor,
                    reason=f'Renewal {subscription.number} starts on {subscription.start_date.isoformat()}.',
                    effective_on=subscription.start_date,
                )
        new_status = Subscription.Status.CONFIRMED
    elif action == 'reopen':
        subscription.quote_valid_until = None
        new_status = Subscription.Status.DRAFT
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
    old = Subscription.objects.select_for_update().select_related('plan', 'customer', 'template').prefetch_related('lines').get(pk=subscription_id)
    if 'renew' not in allowed_actions(old, actor):
        raise PermissionDenied('Renewal is not allowed for this subscription.')
    existing_renewal = old.renewals.order_by('-created_at', '-id').first()
    if existing_renewal:
        if existing_renewal.status in (Subscription.Status.DRAFT, Subscription.Status.QUOTATION):
            return existing_renewal
        raise ValidationError({'code': 'RENEWAL_ALREADY_EXISTS', 'message': 'This subscription already has a renewal. Manage that renewal instead of creating another.'})
    start = old.expiry_date + timedelta(days=1) if old.expiry_date else old.next_billing_date
    if start is None or start <= timezone.localdate():
        raise ValidationError({'code': 'NO_FUTURE_RENEWAL_DATE', 'message': 'The subscription must have a future billing date before it can be renewed.'})
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
        subtotal=old.subtotal,
        discount_total=old.discount_total,
        tax_total=old.tax_total,
        total=old.total,
        plan_base_price_snapshot=old.plan_base_price_snapshot,
        plan_tax_rate_snapshot=old.plan_tax_rate_snapshot,
        minimum_quantity_snapshot=old.minimum_quantity_snapshot,
        allow_pause_snapshot=old.allow_pause_snapshot,
        allow_early_close_snapshot=old.allow_early_close_snapshot,
        allow_renewal_snapshot=old.allow_renewal_snapshot,
        auto_close_on_expiry_snapshot=old.auto_close_on_expiry_snapshot,
        billing_anchor_day=start.day,
        billing_anchor_month=start.month,
        created_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )
    for line in old.lines.all():
        line.pk = None
        line.id = None
        line.subscription = renewed
        line.save()
    SubscriptionEvent.objects.create(subscription=renewed, action='renewal_draft', to_status=Subscription.Status.DRAFT, actor=actor if getattr(actor, 'is_authenticated', False) else None, reason=f'Renewal of {old.number}', effective_on=start)
    return renewed
