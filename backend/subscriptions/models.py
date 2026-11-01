import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from plans.models import Plan


class Subscription(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        QUOTATION = 'quotation', 'Quotation'
        CONFIRMED = 'confirmed', 'Confirmed'
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        EXPIRED = 'expired', 'Expired'
        CLOSED = 'closed', 'Closed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(max_length=24, unique=True, blank=True)
    customer = models.ForeignKey('customers.Customer', related_name='subscriptions', on_delete=models.PROTECT, null=True, blank=True)
    plan = models.ForeignKey('plans.Plan', related_name='subscriptions', on_delete=models.PROTECT, null=True, blank=True)
    plan_base_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    plan_tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    template = models.ForeignKey('quotations.QuoteTemplate', null=True, blank=True, on_delete=models.SET_NULL)
    renewal_of = models.ForeignKey('self', null=True, blank=True, related_name='renewals', on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    cadence = models.CharField(max_length=16, choices=Plan.Cadence.choices, default=Plan.Cadence.MONTHLY)
    start_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField(null=True, blank=True)
    quote_valid_until = models.DateField(null=True, blank=True)
    payment_term_days = models.PositiveSmallIntegerField(default=0)
    currency = models.CharField(max_length=3, default='INR')
    base_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    minimum_quantity_snapshot = models.PositiveIntegerField(default=1)
    allow_pause_snapshot = models.BooleanField(default=False)
    allow_early_close_snapshot = models.BooleanField(default=False)
    allow_renewal_snapshot = models.BooleanField(default=False)
    auto_close_on_expiry_snapshot = models.BooleanField(default=False)
    billing_anchor_day = models.PositiveSmallIntegerField(null=True, blank=True)
    billing_anchor_month = models.PositiveSmallIntegerField(null=True, blank=True)
    next_billing_date = models.DateField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='created_subscriptions', on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['status', 'next_billing_date'])]
        constraints = [
            models.CheckConstraint(
                check=models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=models.F('start_date')),
                name='subscription_expiry_after_start_ck',
            ),
            models.CheckConstraint(
                check=models.Q(subtotal__gte=0, discount_total__gte=0, tax_total__gte=0, total__gte=0),
                name='subscription_totals_nonneg_ck',
            ),
            models.CheckConstraint(
                check=models.Q(discount_total__lte=models.F('subtotal')),
                name='subscription_discount_lte_subtotal_ck',
            ),
            models.CheckConstraint(
                check=(models.Q(billing_anchor_day__isnull=True)
                       | models.Q(billing_anchor_day__gte=1, billing_anchor_day__lte=31)),
                name='subscription_anchor_day_ck',
            ),
            models.CheckConstraint(
                check=(models.Q(billing_anchor_month__isnull=True)
                       | models.Q(billing_anchor_month__gte=1, billing_anchor_month__lte=12)),
                name='subscription_anchor_month_ck',
            ),
        ]

    def save(self, *args, **kwargs):
        creating = self._state.adding
        if creating and self.billing_anchor_day is None:
            self.billing_anchor_day = self.start_date.day
        if creating and self.billing_anchor_month is None:
            self.billing_anchor_month = self.start_date.month
        if creating and not self.number:
            self.number = f'SUB-{self.pk.hex[:12].upper()}'
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number or f'Subscription {self.pk}'


class SubscriptionLine(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="subscription_lines")
    variant = models.ForeignKey(
        "products.ProductVariant",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subscription_lines",
    )
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    taxes = models.ManyToManyField("products.TaxRule", blank=True, related_name="subscription_lines")
    product_name_snapshot = models.CharField(max_length=255, blank=True)
    unit_sales_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    variant_adjustment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    effective_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    line_subtotal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    line_net_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    final_line_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    variant_name_snapshot = models.CharField(max_length=200, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_rate_snapshot = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gte=1), name="subscription_line_quantity_ck"),
            models.CheckConstraint(
                check=models.Q(
                    unit_price__gte=0, gross_amount__gte=0, discount_amount__gte=0,
                    net_amount__gte=0, tax_amount__gte=0,
                ),
                name='subscription_line_amounts_nonneg_ck',
            ),
            models.CheckConstraint(
                check=models.Q(discount_amount__lte=models.F('gross_amount')),
                name='subscription_line_discount_lte_gross_ck',
            ),
        ]

    def clean(self):
        super().clean()
        if self.variant_id and self.product_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "Selected variant does not belong to the selected product."})
        if self.effective_unit_price is not None and self.effective_unit_price < 0:
            raise ValidationError({"effective_unit_price": "Effective unit price cannot be negative."})

    def __str__(self):
        return f"{self.product_name_snapshot or self.product} × {self.quantity}"


class SubscriptionEvent(models.Model):
    subscription = models.ForeignKey(Subscription, related_name='events', on_delete=models.CASCADE)
    action = models.CharField(max_length=24)
    from_status = models.CharField(max_length=16, choices=Subscription.Status.choices, blank=True)
    to_status = models.CharField(max_length=16, choices=Subscription.Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField(blank=True)
    effective_on = models.DateField(default=timezone.localdate, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['effective_on', 'created_at', 'id']
        indexes = [models.Index(fields=['subscription', 'effective_on'])]


class BillingAttempt(models.Model):
    class Result(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCEEDED = 'SUCCEEDED', 'Succeeded'
        FAILED = 'FAILED', 'Failed'
        SKIPPED = 'SKIPPED', 'Skipped'

    subscription = models.ForeignKey(Subscription, related_name='billing_attempts', on_delete=models.CASCADE)
    period_start = models.DateField()
    period_end = models.DateField()
    result = models.CharField(max_length=10, choices=Result.choices, default=Result.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    invoice_id = models.UUIDField(null=True, blank=True, unique=True)
    skip_reason = models.CharField(max_length=120, blank=True)
    last_error = models.TextField(blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['subscription', 'period_start'], name='uniq_billing_subscription_period'),
            models.CheckConstraint(
                check=models.Q(period_end__gt=models.F('period_start')),
                name='billing_attempt_period_valid_ck',
            ),
            models.CheckConstraint(
                check=(models.Q(result='SUCCEEDED', invoice_id__isnull=False)
                       | (~models.Q(result='SUCCEEDED') & models.Q(invoice_id__isnull=True))),
                name='billing_attempt_invoice_state_ck',
            ),
        ]
        ordering = ['period_start']
