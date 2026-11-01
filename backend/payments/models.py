import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Payment(models.Model):
    """Immutable record of money successfully received for an invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    method = models.CharField(max_length=40)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=3)
    received_at = models.DateTimeField()
    note = models.TextField(blank=True)
    reference = models.CharField(max_length=128, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)
        indexes = [
            models.Index(fields=("currency", "received_at"), name="pay_cur_received_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=Q(amount__gt=0), name="payment_amount_positive_ck"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Payment records are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Payment records cannot be deleted.")

    def __str__(self):
        return f"Payment {self.pk} for {self.invoice_id}: {self.amount} {self.currency}"
