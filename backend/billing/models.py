import uuid

from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q


class InvoiceStatus(models.TextChoices):
    DRAFT = "Draft", "Draft"
    CONFIRMED = "Confirmed", "Confirmed"
    PAID = "Paid", "Paid"
    CANCELLED = "Cancelled", "Cancelled"


class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=32, unique=True, editable=False)
    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    customer_id_snapshot = models.PositiveBigIntegerField(null=True, blank=True)
    customer_snapshot = models.JSONField(default=dict, blank=True)
    discount_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    currency = models.CharField(max_length=3, default="INR")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    due_date = models.DateField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("currency", "status", "confirmed_at"), name="inv_cur_stat_conf_idx"),
            models.Index(fields=("currency", "status", "due_date"), name="inv_cur_stat_due_idx"),
            models.Index(fields=("customer_id_snapshot", "status"), name="inv_cust_stat_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("subscription", "period_start"),
                name="inv_sub_period_start_uq",
            ),
            models.CheckConstraint(
                check=Q(period_end__gt=F("period_start")),
                name="billing_invoice_period_valid",
            ),
            models.CheckConstraint(
                check=Q(subtotal__gte=0, discount_total__gte=0, tax_total__gte=0, total__gte=0),
                name="inv_totals_nonneg_ck",
            ),
            models.CheckConstraint(
                check=Q(discount_total__lte=F("subtotal")),
                name="inv_discount_lte_subtotal_ck",
            ),
        ]
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.invoice_number} ({self.status})"


class InvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField()
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    source_type = models.CharField(max_length=32, blank=True)
    source_id = models.CharField(max_length=64, null=True, blank=True)
    product_id_snapshot = models.CharField(max_length=64, blank=True)
    product_name_snapshot = models.CharField(max_length=255, blank=True)
    variant_label_snapshot = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("invoice", "line_number"), name="inv_line_num_uq"),
            models.CheckConstraint(check=Q(quantity__gt=0), name="billing_line_quantity_positive"),
            models.CheckConstraint(
                check=Q(
                    unit_price__gte=0,
                    gross_amount__gte=0,
                    discount_amount__gte=0,
                    taxable_amount__gte=0,
                    tax_amount__gte=0,
                    total_amount__gte=0,
                ),
                name="inv_line_amounts_ck",
            ),
            models.CheckConstraint(
                check=Q(discount_amount__lte=F("gross_amount")),
                name="inv_line_discount_lte_gross_ck",
            ),
        ]
        ordering = ("line_number",)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self._state.adding:
                previous = type(self).objects.select_for_update().only("invoice_id").get(pk=self.pk)
                if previous.invoice_id != self.invoice_id:
                    raise ValueError("An invoice line cannot be moved to another invoice.")
            invoice = Invoice.objects.select_for_update().only("status").get(pk=self.invoice_id)
            if invoice.status != InvoiceStatus.DRAFT:
                raise ValueError("Invoice lines cannot be changed after the invoice leaves Draft.")
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().only("status").get(pk=self.invoice_id)
            if invoice.status != InvoiceStatus.DRAFT:
                raise ValueError("Invoice lines cannot be deleted after the invoice leaves Draft.")
            return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_id} line {self.line_number}: {self.description}"


class InvoiceNumberSequence(models.Model):
    """One allocation row per invoice; the database-generated PK is the sequence."""

    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pk",)


class DocumentJob(models.Model):
    class Kind(models.TextChoices):
        INVOICE_PDF = "invoice_pdf", "Invoice PDF"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="document_jobs")
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.INVOICE_PDF)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    dedupe_key = models.CharField(max_length=200, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    storage_key = models.CharField(max_length=512, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.kind} for {self.invoice.invoice_number} ({self.status})"
