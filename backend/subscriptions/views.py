from decimal import Decimal, InvalidOperation
from datetime import date, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.db import transaction
from django.utils.module_loading import import_string
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from customers.models import Customer
from plans.models import Plan
from products.models import Product, ProductVariant
from quotations.models import QuoteTemplate
from .models import Subscription, SubscriptionEvent, SubscriptionLine
from .services import add_billing_period, allowed_actions, renew, transition
from notifications.services import EmailQueueError, queue_email


class IntegrationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = 'INTEGRATION_UNAVAILABLE'
    default_detail = 'A required pricing or invoice integration is not configured.'


def _staff_required(user):
    if not (user.is_staff or user.is_superuser):
        raise PermissionDenied('Authorized staff access is required.')


def _customer_for(user):
    try:
        return user.customer_profile
    except (AttributeError, ObjectDoesNotExist):
        return None


def _subscription_queryset(request, portal=False):
    qs = Subscription.objects.select_related('customer', 'plan', 'template', 'renewal_of').prefetch_related(
        'lines', 'events', 'billing_attempts', 'invoices'
    )
    if portal:
        customer = _customer_for(request.user)
        if customer is None:
            return qs.none()
        return qs.filter(customer=customer)
    _staff_required(request.user)
    return qs


def _pricing(plan, lines, effective_date):
    """Use Aby's agreed pricing contract. Never trust client totals."""
    try:
        calculate_price = import_string(getattr(settings, 'SUBSCRIPTION_PRICING_PROVIDER', ''))
    except (ImportError, AttributeError, ValueError) as exc:
        raise IntegrationUnavailable('Aby pricing service is not installed yet.') from exc
    result = calculate_price(plan=plan, lines=lines, effective_date=effective_date)
    if not isinstance(result, dict) or 'lines' not in result or 'subtotal' not in result or 'final_total' not in result:
        raise IntegrationUnavailable('Aby pricing service returned an invalid pricing breakdown.')
    return result


def _serialize_line(line):
    return {
        'id': line.pk,
        'product_id': line.product_id,
        'variant_id': line.variant_id,
        'product_name': line.product_name_snapshot,
        'variant_name': line.variant_name_snapshot,
        'quantity': line.quantity,
        'unit_price': str(line.unit_price),
        'gross_amount': str(line.gross_amount),
        'discount_amount': str(line.discount_amount),
        'tax_rate': str(line.tax_rate_snapshot or 0),
        'tax_amount': str(line.tax_amount),
        'net_amount': str(line.net_amount),
    }


def _serialize(subscription, portal=False):
    events = [
        {
            'action': e.action,
            'from': e.from_status or None,
            'to': e.to_status,
            'effective_on': e.effective_on.isoformat(),
            'reason': '' if portal else e.reason,
        }
        for e in subscription.events.all()
    ]
    data = {
        'id': subscription.pk,
        'number': subscription.number,
        'customer_id': subscription.customer_id,
        'customer': subscription.customer.name,
        'plan_id': subscription.plan_id,
        'plan': subscription.plan.name,
        'template_id': subscription.template_id,
        'renewal_of_id': subscription.renewal_of_id,
        'status': subscription.status.upper(),
        'cadence': subscription.cadence,
        'start_date': subscription.start_date.isoformat(),
        'expiry_date': subscription.expiry_date.isoformat() if subscription.expiry_date else None,
        'quote_valid_until': subscription.quote_valid_until.isoformat() if subscription.quote_valid_until else None,
        'payment_term_days': subscription.payment_term_days,
        'next_billing_date': subscription.next_billing_date.isoformat() if subscription.next_billing_date else None,
        'currency': subscription.currency,
        'subtotal': str(subscription.subtotal),
        'discount_total': str(subscription.discount_total),
        'tax_total': str(subscription.tax_total),
        'total': str(subscription.total),
        'lines': [_serialize_line(line) for line in subscription.lines.all()],
        'timeline': events,
        'allowed_actions': [a for a in allowed_actions(subscription) if a in {'pause', 'resume', 'close', 'renew'}] if portal else allowed_actions(subscription),
        'created_at': subscription.created_at.isoformat(),
    }
    invoices = list(subscription.invoices.all())
    if portal:
        # Draft invoices are internal until staff confirm them.
        invoices = [invoice for invoice in invoices if invoice.status in {'Confirmed', 'Paid'}]
    invoices.sort(key=lambda invoice: (invoice.period_start, invoice.created_at))
    data['invoices'] = [
        {
            'id': str(invoice.pk),
            'period_start': invoice.period_start.isoformat(),
            'period_end': invoice.period_end.isoformat(),
            'status': invoice.status,
            'currency': invoice.currency,
            'total': str(invoice.total),
            'due_date': invoice.due_date.isoformat() if invoice.due_date else None,
        }
        for invoice in invoices
    ]
    return data


def _resolve_ids(customer_id, plan_id, template_id=None):
    try:
        customer = Customer.objects.get(pk=customer_id)
    except (Customer.DoesNotExist, TypeError, ValueError):
        raise ValidationError({'customer_id': 'Select an existing customer.'})
    template = None
    if template_id:
        try:
            template = QuoteTemplate.objects.get(pk=template_id, is_active=True)
        except (QuoteTemplate.DoesNotExist, TypeError, ValueError):
            raise ValidationError({'template_id': 'Select an active quotation template.'})
        if not template.plan.is_active:
            raise ValidationError({'template_id': 'The quotation template uses an inactive plan.'})
    if template:
        plan = template.plan
    else:
        try:
            plan = Plan.objects.get(pk=plan_id, is_active=True)
        except (Plan.DoesNotExist, TypeError, ValueError):
            raise ValidationError({'plan_id': 'Select an active plan.'})
    return customer, plan, template


def _save_priced_lines(subscription, pricing, submitted_lines):
    priced_lines = pricing['lines']
    if not isinstance(priced_lines, list) or any(not isinstance(line, dict) for line in priced_lines):
        raise IntegrationUnavailable('Pricing breakdown lines must be a list of objects.')
    if len(priced_lines) != len(submitted_lines):
        raise IntegrationUnavailable('Pricing breakdown did not match the requested lines.')
    objects = []
    for requested, priced in zip(submitted_lines, priced_lines):
        try:
            priced_quantity = _integer_input(priced.get('quantity', requested.get('quantity', 0)), minimum=1)
        except ValueError:
            raise IntegrationUnavailable('Pricing breakdown contains an invalid quantity.')
        try:
            requested_quantity = _integer_input(requested.get('quantity', 0), minimum=1)
        except ValueError:
            raise ValidationError({'lines': 'Line quantities must be positive integers.'})
        if (str(priced.get('product_id')) != str(requested.get('product_id'))
                or priced_quantity != requested_quantity
                or ('variant_id' in priced and str(priced.get('variant_id') or '') != str(requested.get('variant_id') or ''))):
            raise IntegrationUnavailable('Pricing breakdown does not match the requested products and quantities.')
        try:
            product = Product.objects.get(pk=requested['product_id'], is_active=True)
        except (Product.DoesNotExist, KeyError, TypeError, ValueError):
            raise ValidationError({'lines': 'Each line must reference an active product.'})
        variant = None
        if requested.get('variant_id'):
            try:
                variant_id = _integer_input(requested['variant_id'], minimum=1)
                variant = ProductVariant.objects.get(pk=variant_id, product=product, is_active=True)
            except (ProductVariant.DoesNotExist, TypeError, ValueError):
                raise ValidationError({'lines': 'A selected variant must belong to its product and be active.'})
        try:
            quantity = _integer_input(requested.get('quantity', 0), minimum=1)
        except ValueError:
            raise ValidationError({'lines': 'Line quantities must be positive integers.'})
        try:
            unit_price = _price_decimal(_required_price(priced, 'effective_unit_price', 'unit_price'))
            unit_sales_price = _price_decimal(priced.get('unit_sales_price', product.sales_price))
            variant_adjustment = _signed_price_decimal(
                priced.get('variant_adjustment', unit_price - unit_sales_price)
            )
            gross_amount = _price_decimal(_required_price(priced, 'line_subtotal', 'gross_amount', 'subtotal'))
            discount_amount = _price_decimal(priced.get('discount_amount', 0))
            tax_rate = _price_decimal(priced.get('tax_rate', 0))
            tax_amount = _price_decimal(priced.get('tax_amount', 0))
            net_amount = _price_decimal(_required_price(priced, 'line_net_amount', 'net_amount', 'total'))
            final_line_total = _price_decimal(priced.get('final_line_total', net_amount + tax_amount))
            if not variant_adjustment.is_finite() or unit_sales_price + variant_adjustment != unit_price:
                raise ValueError('Pricing returned inconsistent unit price snapshots.')
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise IntegrationUnavailable('Pricing breakdown contains a missing or invalid amount.') from exc
        if unit_sales_price + variant_adjustment != unit_price:
            raise IntegrationUnavailable('Pricing breakdown unit price does not match its saved price components.')
        if gross_amount - discount_amount != net_amount or net_amount + tax_amount != final_line_total:
            raise IntegrationUnavailable('Pricing breakdown line amounts do not reconcile.')
        variant_name = str(priced.get('variant_label') or (f'{variant.attribute_label}: {variant.option_value}' if variant else ''))
        objects.append(SubscriptionLine(
            subscription=subscription,
            product=product,
            variant=variant,
            product_name_snapshot=str(priced.get('product_name') or product.name),
            variant_name_snapshot=variant_name,
            quantity=quantity,
            unit_sales_price=unit_sales_price,
            variant_adjustment=variant_adjustment,
            effective_unit_price=unit_price,
            line_subtotal=gross_amount,
            line_net_amount=net_amount,
            tax_rate=tax_rate,
            final_line_total=final_line_total,
            unit_price=unit_price,
            unit_sales_price=unit_sales_price,
            variant_adjustment=variant_adjustment,
            gross_amount=gross_amount,
            discount_amount=discount_amount,
            tax_rate=tax_rate,
            tax_rate_snapshot=tax_rate,
            tax_amount=tax_amount,
            net_amount=net_amount,
            sort_order=len(objects),
        ))
    SubscriptionLine.objects.bulk_create(objects)


def _save_totals(subscription, pricing):
    try:
        subscription.subtotal = _price_decimal(pricing['subtotal'])
        subscription.discount_total = _price_decimal(pricing['total_discount'])
        subscription.tax_total = _price_decimal(pricing['total_tax'])
        subscription.total = _price_decimal(pricing['final_total'])
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise IntegrationUnavailable('Pricing breakdown contains invalid totals.') from exc
    plan_summary = pricing.get('plan_summary') or {}
    if not isinstance(plan_summary, dict):
        raise IntegrationUnavailable('Pricing plan summary must be an object.')
    try:
        plan_subtotal = _price_decimal(plan_summary.get('base_fee', 0))
        plan_discount = _price_decimal(plan_summary.get('discount_amount', 0))
        plan_tax = _price_decimal(plan_summary.get('tax_amount', 0))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise IntegrationUnavailable('Pricing breakdown contains invalid plan totals.') from exc
    lines = list(subscription.lines.all())
    line_subtotal = sum((line.gross_amount for line in lines), Decimal('0.00'))
    line_discount = sum((line.discount_amount for line in lines), Decimal('0.00'))
    line_tax = sum((line.tax_amount for line in lines), Decimal('0.00'))
    if subscription.subtotal != plan_subtotal + line_subtotal:
        raise IntegrationUnavailable('Pricing subtotal does not match its plan and line snapshots.')
    if subscription.discount_total != plan_discount + line_discount:
        raise IntegrationUnavailable('Pricing discount total does not match its plan and line snapshots.')
    if subscription.tax_total != plan_tax + line_tax:
        raise IntegrationUnavailable('Pricing tax total does not match its plan and line snapshots.')
    if subscription.total != subscription.subtotal - subscription.discount_total + subscription.tax_total:
        raise IntegrationUnavailable('Pricing totals do not reconcile.')
    currency = str(pricing.get('currency', subscription.currency)).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise IntegrationUnavailable('Pricing breakdown currency must be a three-letter code.')
    subscription.currency = currency
    subscription.save(update_fields=['currency', 'subtotal', 'discount_total', 'tax_total', 'total', 'updated_at'])


def _price_decimal(value):
    if isinstance(value, float):
        raise ValueError('Prices must be supplied as decimal values, not floating point values.')
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError('Prices must be finite and non-negative.')
    return amount


def _signed_price_decimal(value):
    if isinstance(value, float):
        raise ValueError('Price components must be supplied as decimal values, not floating point values.')
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError('Price components must be finite.')
    return amount


def _required_price(values, *keys):
    for key in keys:
        if key in values:
            return values[key]
    raise KeyError(keys[0])


def _price_input(data, template):
    lines = data.get('lines')
    if lines is None and template:
        lines = template.default_lines
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        raise ValidationError({'lines': 'Expected a list of product lines.'})
    return lines


def _validate_requested_lines(lines, minimum_quantity):
    if any(not isinstance(line, dict) for line in lines):
        raise ValidationError({'lines': 'Each line must be an object with a product ID and quantity.'})
    try:
        quantities = [_integer_input(line.get('quantity', 0), minimum=1) for line in lines]
        for line in lines:
            _integer_input(line.get('product_id', 0), minimum=1)
            if line.get('variant_id') not in (None, ''):
                _integer_input(line['variant_id'], minimum=1)
    except (TypeError, ValueError):
        raise ValidationError({'lines': 'Each line needs valid product and variant IDs and a positive integer quantity.'})
    if any(quantity < 1 for quantity in quantities):
        raise ValidationError({'lines': 'Line quantities must be positive integers.'})
    if sum(quantities) < minimum_quantity:
        raise ValidationError({'lines': f'This plan requires a total product quantity of at least {minimum_quantity}.'})


def _is_complete_cycle_end(
    start: date,
    expiry: date,
    cadence: str,
    anchor_day: int | None = None,
    anchor_month: int | None = None,
) -> bool:
    cursor = start
    for _ in range(100000):
        next_start = add_billing_period(
            cursor, cadence, anchor_day or start.day, anchor_month or start.month
        )
        cycle_end = next_start - timedelta(days=1)
        if cycle_end == expiry:
            return True
        if cycle_end > expiry:
            return False
        cursor = next_start
    return False


def _integer_input(value, minimum=0):
    if isinstance(value, bool):
        raise ValueError('Booleans are not integer inputs.')
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ValueError('Expected a whole number.')
    if parsed < minimum:
        raise ValueError('Value is below the allowed minimum.')
    return parsed


class SubscriptionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _subscription_queryset(request)
        for field in ('customer_id', 'plan_id', 'status'):
            value = request.query_params.get(field.removesuffix('_id') if field == 'status' else field)
            if field == 'status' and value:
                value = value.lower()
            if value:
                qs = qs.filter(**{field: value})
        due = request.query_params.get('due')
        if due == 'true':
            qs = qs.filter(next_billing_date__lte=timezone.localdate())
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(number__icontains=search) | qs.filter(customer__name__icontains=search)
        paginator = self.paginator
        page = paginator.paginate_queryset(qs.distinct(), request, view=self)
        return paginator.get_paginated_response([_serialize(item) for item in page])

    @property
    def paginator(self):
        if not hasattr(self, '_paginator'):
            from rest_framework.pagination import PageNumberPagination
            self._paginator = PageNumberPagination()
            self._paginator.page_size = 25
            self._paginator.max_page_size = 100
            self._paginator.page_size_query_param = 'page_size'
        return self._paginator

    @transaction.atomic
    def post(self, request):
        _staff_required(request.user)
        customer, plan, template = _resolve_ids(request.data.get('customer_id'), request.data.get('plan_id'), request.data.get('template_id'))
        start = request.data.get('start_date')
        expiry = request.data.get('expiry_date')
        try:
            start_date = date.fromisoformat(start)
            expiry_date = date.fromisoformat(expiry) if expiry else None
        except (TypeError, ValueError):
            raise ValidationError({'start_date': 'Use YYYY-MM-DD dates.'})
        if expiry_date and expiry_date < start_date:
            raise ValidationError({'expiry_date': 'Expiry cannot be before the start date.'})
        today = timezone.localdate()
        if expiry_date and not _is_complete_cycle_end(start_date, expiry_date, plan.cadence):
            raise ValidationError({'expiry_date': 'Expiry must align with the end of a complete billing cycle; proration is not supported.'})
        if (plan.available_from and start_date < plan.available_from) or (plan.available_until and start_date > plan.available_until):
            raise ValidationError({'plan_id': 'Plan is not available on the selected start date.'})
        lines = _price_input(request.data, template)
        _validate_requested_lines(lines, plan.minimum_quantity)
        pricing = _pricing(plan, lines, start_date)
        plan_tax_rate = sum(
            (tax.percentage_rate for tax in plan.taxes.filter(is_active=True)),
            Decimal('0.00'),
        )
        try:
            default_term = getattr(getattr(template, 'payment_term', None), 'days_until_due', None)
            if default_term is None:
                default_term = getattr(getattr(plan, 'payment_term', None), 'days_until_due', 0)
            term = _integer_input(request.data.get('payment_term_days', default_term), minimum=0)
        except ValueError:
            raise ValidationError({'payment_term_days': 'Expected a non-negative integer.'})
        subscription = Subscription.objects.create(
            customer=customer,
            plan=plan,
            template=template,
            status=Subscription.Status.DRAFT,
            cadence=plan.cadence,
            start_date=start_date,
            expiry_date=expiry_date,
            payment_term_days=term,
            currency=pricing.get('currency', 'INR'),
            base_price_snapshot=plan.base_price,
            plan_base_price_snapshot=plan.base_price,
            plan_tax_rate_snapshot=plan_tax_rate,
            minimum_quantity_snapshot=plan.minimum_quantity,
            allow_pause_snapshot=plan.allow_pause,
            allow_early_close_snapshot=plan.allow_early_closure,
            allow_renewal_snapshot=plan.allow_renewal,
            auto_close_on_expiry_snapshot=plan.auto_close,
            billing_anchor_day=start_date.day,
            billing_anchor_month=start_date.month,
            created_by=request.user,
        )
        _save_priced_lines(subscription, pricing, lines)
        _save_totals(subscription, pricing)
        SubscriptionEvent.objects.create(subscription=subscription, action='created', to_status=subscription.status, actor=request.user, effective_on=today)
        return Response(_serialize(subscription), status=status.HTTP_201_CREATED)


class SubscriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        try:
            return _subscription_queryset(request).get(pk=pk)
        except Subscription.DoesNotExist:
            raise NotFound('Subscription not found.')

    def get(self, request, pk):
        return Response(_serialize(self.get_object(request, pk)))

    @transaction.atomic
    def patch(self, request, pk):
        _staff_required(request.user)
        editable_fields = {'start_date', 'expiry_date', 'payment_term_days', 'lines'}
        unknown_fields = set(request.data) - editable_fields
        if unknown_fields:
            raise ValidationError({field: 'This field cannot be edited on a draft subscription.' for field in unknown_fields})
        try:
            subscription = Subscription.objects.select_for_update().select_related('plan', 'customer', 'template').get(pk=pk)
        except Subscription.DoesNotExist:
            raise NotFound('Subscription not found.')
        if subscription.status != Subscription.Status.DRAFT:
            raise ValidationError({'code': 'NOT_EDITABLE', 'message': 'Only draft subscriptions can be edited.'})
        if 'status' in request.data:
            raise ValidationError({'status': 'Use a lifecycle action endpoint to change status.'})
        start_date = subscription.start_date
        expiry_date = subscription.expiry_date
        try:
            if 'start_date' in request.data:
                start_date = date.fromisoformat(request.data['start_date'])
            if 'expiry_date' in request.data:
                expiry_date = date.fromisoformat(request.data['expiry_date']) if request.data['expiry_date'] else None
        except (TypeError, ValueError):
            raise ValidationError({'dates': 'Use YYYY-MM-DD dates.'})
        if expiry_date and expiry_date < start_date:
            raise ValidationError({'expiry_date': 'Expiry cannot be before the start date.'})
        if expiry_date and not _is_complete_cycle_end(
            start_date,
            expiry_date,
            subscription.cadence,
            start_date.day if 'start_date' in request.data else subscription.billing_anchor_day,
            start_date.month if 'start_date' in request.data else subscription.billing_anchor_month,
        ):
            raise ValidationError({'expiry_date': 'Expiry must align with the end of a complete billing cycle; proration is not supported.'})
        if 'lines' in request.data:
            lines = _price_input(request.data, None)
        elif 'start_date' in request.data:
            lines = [
                {'product_id': line.product_id, 'variant_id': line.variant_id, 'quantity': line.quantity}
                for line in subscription.lines.all()
            ]
        else:
            lines = None
        if lines is not None:
            _validate_requested_lines(lines, subscription.minimum_quantity_snapshot)
            pricing = _pricing(subscription.plan, lines, start_date)
        else:
            pricing = None
        subscription.start_date = start_date
        if 'start_date' in request.data:
            subscription.billing_anchor_day = start_date.day
            subscription.billing_anchor_month = start_date.month
        subscription.expiry_date = expiry_date
        if 'start_date' in request.data:
            subscription.billing_anchor_day = start_date.day
            subscription.billing_anchor_month = start_date.month
        if 'payment_term_days' in request.data:
            try:
                subscription.payment_term_days = _integer_input(request.data['payment_term_days'], minimum=0)
            except ValueError:
                raise ValidationError({'payment_term_days': 'Expected a non-negative integer.'})
        subscription.save()
        if pricing is not None:
            subscription.lines.all().delete()
            _save_priced_lines(subscription, pricing, lines)
            _save_totals(subscription, pricing)
        return Response(_serialize(subscription))


class SubscriptionActionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk, action):
        _staff_required(request.user)
        if action == 'renew':
            renewed = renew(pk, request.user)
            return Response(_serialize(renewed), status=status.HTTP_201_CREATED)
        if action == 'send':
            try:
                subscription = _subscription_queryset(request).get(pk=pk)
            except Subscription.DoesNotExist:
                raise NotFound('Subscription not found.')
            if subscription.status != Subscription.Status.QUOTATION:
                raise ValidationError({'status': 'Only an open quotation can be sent.'})
            if subscription.quote_valid_until and subscription.quote_valid_until < timezone.localdate():
                raise ValidationError({'code': 'QUOTE_EXPIRED', 'message': 'This quotation has expired.'})
            customer = subscription.customer
            if not customer or not customer.email:
                raise ValidationError({'customer': 'The customer needs an email address before the quotation can be sent.'})
            try:
                result = queue_email(
                    'subscription_quote', customer.email,
                    {'customer_name': customer.name, 'subscription_number': subscription.number,
                     'plan_name': subscription.plan.name, 'currency': subscription.currency,
                     'total': str(subscription.total),
                     'valid_until': subscription.quote_valid_until.isoformat() if subscription.quote_valid_until else ''},
                    f'subscription:{subscription.pk}:quote:{subscription.quote_valid_until}',
                )
            except (EmailQueueError, DjangoValidationError, ValueError) as exc:
                raise ValidationError({'email': str(exc)})
            from notifications.models import EmailOutbox
            email = EmailOutbox.objects.get(pk=result.email_id)
            return Response({'email_id': str(email.pk), 'status': email.status, 'recipient': email.recipient}, status=status.HTTP_202_ACCEPTED)
        try:
            sub = transition(pk, action, actor=request.user, reason=request.data.get('reason', ''))
        except Subscription.DoesNotExist:
            raise NotFound('Subscription not found.')
        return Response(_serialize(sub))


class PortalSubscriptionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = _subscription_queryset(request, portal=True)
        status_filter = request.query_params.get('status', '').strip().lower()
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(number__icontains=search)
        paginator = SubscriptionListCreateView().paginator
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([_serialize(item, portal=True) for item in page])


class PortalSubscriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        try:
            return _subscription_queryset(request, portal=True).get(pk=pk)
        except Subscription.DoesNotExist:
            raise NotFound('Subscription not found.')

    def get(self, request, pk):
        return Response(_serialize(self.get_object(request, pk), portal=True))


class PortalSubscriptionActionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk, action):
        try:
            subscription = _subscription_queryset(request, portal=True).get(pk=pk)
        except Subscription.DoesNotExist:
            raise NotFound('Subscription not found.')
        if action not in {'pause', 'resume', 'close', 'renew'}:
            raise NotFound('Subscription action not found.')
        if action == 'renew':
            renewed = renew(subscription.pk, request.user)
            return Response(_serialize(renewed, portal=True), status=status.HTTP_201_CREATED)
        updated = transition(subscription.pk, action, actor=request.user, reason=request.data.get('reason', ''))
        return Response(_serialize(updated, portal=True))
