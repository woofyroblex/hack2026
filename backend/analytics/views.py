"""Read-only financial reports, using issued invoices and recorded receipts."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Invoice, InvoiceStatus
from config.catalog_views import CatalogPagination
from customers.models import Customer
from payments.models import Payment
from subscriptions.models import Subscription

MONEY = DecimalField(max_digits=18, decimal_places=2)


def money(value):
    return format(value or Decimal('0'), '.2f')


def report_filters(request):
    currency = request.query_params.get('currency', 'INR').upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValidationError({'currency': 'Use a three-letter currency code.'})
    dates = {}
    for key in ['date_from', 'date_to']:
        raw = request.query_params.get(key)
        if raw:
            try:
                dates[key] = date.fromisoformat(raw)
            except ValueError:
                raise ValidationError({key: 'Use YYYY-MM-DD.'})
    if len(dates) == 2 and dates['date_from'] > dates['date_to']:
        raise ValidationError({'date_to': 'End date must be on or after start date.'})
    return currency, dates


def dated(queryset, field, dates):
    if 'date_from' in dates:
        queryset = queryset.filter(**{field + '__gte': dates['date_from']})
    if 'date_to' in dates:
        queryset = queryset.filter(**{field + '__lte': dates['date_to']})
    return queryset


def issued(currency):
    paid = Payment.objects.filter(invoice_id=OuterRef('pk')).values('invoice_id').annotate(total=Sum('amount')).values('total')
    return Invoice.objects.filter(currency=currency, status__in=[InvoiceStatus.CONFIRMED, InvoiceStatus.PAID]).annotate(
        amount_paid=Coalesce(Subquery(paid, output_field=MONEY), Value(Decimal('0')), output_field=MONEY),
    ).annotate(balance=F('total') - F('amount_paid'))


class SummaryView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        currency, dates = report_filters(request)
        invoices = dated(issued(currency), 'confirmed_at__date', dates).annotate(
            billed_amount=F('total') - F('tax_total'),
        )
        current_invoices = issued(currency)
        payments = dated(Payment.objects.filter(currency=currency), 'received_at__date', dates)
        billed = invoices.aggregate(total=Sum('billed_amount'))['total']
        outstanding = current_invoices.aggregate(total=Sum('balance'))['total']
        overdue = current_invoices.filter(
            due_date__lt=timezone.localdate(), balance__gt=0,
        ).aggregate(total=Sum('balance'))['total']
        return Response({
            'currency': currency,
            'active_subscriptions': Subscription.objects.filter(status=Subscription.Status.ACTIVE, currency=currency).count(),
            'customers': Customer.objects.count(),
            'billed': money(billed),
            'collected': money(payments.aggregate(total=Sum('amount'))['total']),
            'outstanding': money(outstanding), 'overdue': money(overdue),
        })


class RevenueView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        currency, dates = report_filters(request)
        invoices = dated(issued(currency), 'confirmed_at__date', dates).annotate(
            billed_amount=F('total') - F('tax_total'),
        )
        payments = dated(Payment.objects.filter(currency=currency), 'received_at__date', dates)
        buckets = defaultdict(lambda: {'billed': Decimal('0'), 'collected': Decimal('0')})
        for queryset, field, metric in [(invoices, 'confirmed_at', 'billed'), (payments, 'received_at', 'collected')]:
            amount_field = 'billed_amount' if metric == 'billed' else 'amount'
            for row in queryset.annotate(month=TruncMonth(field)).values('month').annotate(amount=Sum(amount_field)).order_by('month'):
                if row['month']:
                    buckets[row['month'].strftime('%Y-%m')][metric] += row['amount']
        return Response({'currency': currency, 'results': [
            {'month': month, **{key: money(value) for key, value in amounts.items()}}
            for month, amounts in sorted(buckets.items())
        ]})


class OverdueView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        currency, _dates = report_filters(request)
        queryset = issued(currency).filter(
            due_date__lt=timezone.localdate(), balance__gt=0,
        ).select_related('subscription__customer').order_by('due_date', 'id')
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search)
                | Q(subscription__customer__name__icontains=search)
                | Q(customer_snapshot__name__icontains=search)
            )
        paginator = CatalogPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([{
            'id': str(item.id), 'invoice_number': item.invoice_number,
            'customer_name': item.customer_snapshot.get('name') or item.subscription.customer.name,
            'status': item.status, 'currency': item.currency, 'total': money(item.total),
            'amount_paid': money(item.amount_paid), 'balance': money(item.balance),
            'due_date': item.due_date.isoformat(), 'days_overdue': (timezone.localdate() - item.due_date).days,
        } for item in page])


class PortalSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            customer = request.user.customer_profile
        except (AttributeError, Customer.DoesNotExist):
            customer = None
        if customer is None:
            return Response({
                'currency': 'INR', 'active_subscriptions': 0, 'total_subscriptions': 0,
                'issued_invoices': 0, 'outstanding': '0.00', 'next_billing_date': None,
            })
        subscriptions = Subscription.objects.filter(customer=customer)
        active = subscriptions.filter(status=Subscription.Status.ACTIVE)
        invoices = issued('INR').filter(
            Q(customer_id_snapshot=customer.pk)
            | Q(customer_id_snapshot__isnull=True, subscription__customer=customer)
        )
        outstanding = invoices.aggregate(total=Sum('balance'))['total']
        return Response({
            'currency': 'INR',
            'active_subscriptions': active.count(),
            'total_subscriptions': subscriptions.count(),
            'issued_invoices': invoices.count(),
            'outstanding': money(outstanding),
            'next_billing_date': active.filter(next_billing_date__isnull=False).order_by('next_billing_date').values_list('next_billing_date', flat=True).first(),
        })
