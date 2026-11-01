"""Retry-safe subscription-cycle orchestration; invoice rows belong to Abin's app."""
from __future__ import annotations
from datetime import date
from importlib import import_module

from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from subscriptions.models import BillingAttempt, Subscription, SubscriptionEvent
from subscriptions.services import add_billing_period, period_end

CATCH_UP_BATCH_SIZE = 5


def _status_on(subscription: Subscription, day: date) -> str:
    events = list(subscription.events.filter(effective_on__lte=day).order_by('effective_on', 'created_at', 'id'))
    if not events:
        return subscription.status
    status = Subscription.Status.DRAFT
    for event in events:
        status = event.to_status
    return status


def _invoice_creator():
    """Resolve Abin's invoice contract from the existing billing app when available."""
    for module_name in ('billing.services', 'invoices.services'):
        try:
            service = import_module(module_name)
            return service.create_invoice_for_period
        except (ImportError, AttributeError):
            continue
    raise RuntimeError('Invoice integration is not ready: implement billing.services.create_invoice_for_period(subscription_id, period_start, period_end).')


def _set_next_cycle(subscription: Subscription, start: date, today: date, skip_reason: str = '') -> None:
    if skip_reason.startswith('At or after') or 'closed' in skip_reason.lower() or 'expired' in skip_reason.lower():
        subscription.next_billing_date = None
    elif 'paused' in skip_reason.lower():
        # Keep the cursor at the next active cycle if a customer has already resumed.
        # This lets older unpaid active cycles be caught up before paused periods are skipped.
        candidate = add_billing_period(start, subscription.cadence, subscription.billing_anchor_day, subscription.billing_anchor_month)
        for _ in range(100000):
            if subscription.expiry_date and candidate > subscription.expiry_date:
                subscription.next_billing_date = None
                break
            if _status_on(subscription, candidate) == Subscription.Status.ACTIVE:
                subscription.next_billing_date = candidate
                break
            if candidate > today:
                subscription.next_billing_date = None
                break
            candidate = add_billing_period(candidate, subscription.cadence, subscription.billing_anchor_day, subscription.billing_anchor_month)
        else:
            subscription.next_billing_date = None
    else:
        subscription.next_billing_date = add_billing_period(start, subscription.cadence, subscription.billing_anchor_day, subscription.billing_anchor_month)
    subscription.save(update_fields=['next_billing_date', 'updated_at'])


@transaction.atomic
def process_one_cycle(subscription_id: int, today: date | None = None) -> tuple[str, str]:
    today = today or timezone.localdate()
    # Lock only the subscription row; plan/customer joins can be nullable in legacy records.
    subscription = Subscription.objects.select_for_update(of=('self',)).select_related('plan', 'customer').get(pk=subscription_id)
    start = subscription.next_billing_date
    if not start or start > today:
        return 'NOT_DUE', ''
    end = period_end(subscription, start)
    attempt, _ = BillingAttempt.objects.select_for_update().get_or_create(
        subscription=subscription,
        period_start=start,
        defaults={'period_end': end},
    )
    attempt.period_end = end
    if attempt.result == BillingAttempt.Result.SUCCEEDED:
        _set_next_cycle(subscription, start, today)
        return 'EXISTS', ''
    if attempt.result == BillingAttempt.Result.SKIPPED:
        _set_next_cycle(subscription, start, today, attempt.skip_reason)
        return 'SKIPPED', attempt.skip_reason

    eligible = start >= subscription.start_date
    if subscription.expiry_date and start > subscription.expiry_date:
        eligible = False
    state_at_period = _status_on(subscription, start)
    eligible = eligible and state_at_period == Subscription.Status.ACTIVE
    if not eligible:
        if start < subscription.start_date:
            reason = 'Before subscription start'
        elif subscription.expiry_date and start > subscription.expiry_date:
            reason = 'At or after subscription expiry'
        else:
            reason = f'Service was {state_at_period.lower()} for this period'
        attempt.result = BillingAttempt.Result.SKIPPED
        attempt.skip_reason = reason
        attempt.completed_at = timezone.now()
        attempt.save()
        _set_next_cycle(subscription, start, today, reason)
        return 'SKIPPED', reason

    attempt.result = BillingAttempt.Result.PENDING
    attempt.attempt_count += 1
    attempt.attempted_at = timezone.now()
    attempt.last_error = ''
    attempt.save()
    try:
        # Isolate a failed invoice insert in a savepoint so the failed-attempt record can commit.
        with transaction.atomic():
            invoice = _invoice_creator()(subscription_id=subscription.pk, period_start=start, period_end=end)
        invoice_id = getattr(invoice, 'pk', invoice if isinstance(invoice, int) else None)
        if invoice_id is None:
            raise RuntimeError('Invoice service must return an invoice or its integer ID.')
    except Exception as exc:
        attempt.result = BillingAttempt.Result.FAILED
        attempt.last_error = str(exc)[:4000]
        attempt.save(update_fields=['result', 'last_error', 'attempt_count', 'attempted_at', 'period_end'])
        return 'FAILED', attempt.last_error

    attempt.result = BillingAttempt.Result.SUCCEEDED
    attempt.invoice_id = invoice_id
    attempt.completed_at = timezone.now()
    attempt.save()
    _set_next_cycle(subscription, start, today)
    return 'SUCCEEDED', ''


def scan_due_subscriptions(today: date | None = None, limit: int = 100) -> dict:
    today = today or timezone.localdate()
    scanned = succeeded = skipped = failed = 0
    # Include terminal/paused subscriptions: their earlier eligible periods can still be owed after downtime.
    ids = list(Subscription.objects.filter(next_billing_date__lte=today).exclude(next_billing_date__isnull=True).order_by('next_billing_date').values_list('id', flat=True)[:limit])
    for subscription_id in ids:
        for _ in range(CATCH_UP_BATCH_SIZE):
            result, _detail = process_one_cycle(subscription_id, today)
            if result == 'NOT_DUE':
                break
            scanned += 1
            if result in {'SUCCEEDED', 'EXISTS'}:
                succeeded += 1
            elif result == 'SKIPPED':
                skipped += 1
            elif result == 'FAILED':
                failed += 1
                break
        # Remaining due cycles stay at the cursor and are picked up by the next task run.
    return {'scanned': scanned, 'succeeded': succeeded, 'skipped': skipped, 'failed': failed}


@transaction.atomic
def advance_lifecycle(today: date | None = None) -> dict:
    today = today or timezone.localdate()
    activated = expired = closed = 0
    future = Subscription.objects.filter(status=Subscription.Status.CONFIRMED, start_date__lte=today).select_for_update()
    for sub in future:
        previous = sub.status
        sub.status = Subscription.Status.ACTIVE
        sub.next_billing_date = sub.start_date
        sub.save(update_fields=['status', 'next_billing_date', 'updated_at'])
        SubscriptionEvent.objects.create(subscription=sub, action='scheduled_activation', from_status=previous, to_status=sub.status, effective_on=sub.start_date)
        activated += 1
    current = Subscription.objects.filter(status__in=[Subscription.Status.ACTIVE, Subscription.Status.PAUSED], expiry_date__lt=today).select_for_update()
    for sub in current:
        previous = sub.status
        target = Subscription.Status.CLOSED if sub.auto_close_on_expiry_snapshot else Subscription.Status.EXPIRED
        sub.status = target
        sub.save(update_fields=['status', 'updated_at'])
        SubscriptionEvent.objects.create(subscription=sub, action='expiry', from_status=previous, to_status=target, effective_on=sub.expiry_date + timedelta(days=1))
        if target == Subscription.Status.CLOSED:
            closed += 1
        else:
            expired += 1
    return {'activated': activated, 'expired': expired, 'closed': closed}
