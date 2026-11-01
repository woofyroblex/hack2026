"""Staff-only searchable payment history."""

from datetime import date
from uuid import UUID

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.catalog_views import CatalogPagination
from .models import Payment


class PaymentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Authorized staff access is required.")

        queryset = Payment.objects.select_related(
            "invoice", "invoice__subscription__customer"
        ).order_by("-received_at", "-id")

        currency = request.query_params.get("currency", "").strip().upper()
        if currency:
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise ValidationError({"currency": "Use a three-letter currency code."})
            queryset = queryset.filter(currency=currency)

        method = request.query_params.get("method", "").strip()
        if method:
            queryset = queryset.filter(method__iexact=method)

        invoice_id = request.query_params.get("invoice_id", "").strip()
        if invoice_id:
            try:
                invoice_id = UUID(invoice_id)
            except ValueError:
                raise ValidationError({"invoice_id": "Expected an invoice UUID."})
            queryset = queryset.filter(invoice_id=invoice_id)

        date_from = request.query_params.get("date_from", "").strip()
        date_to = request.query_params.get("date_to", "").strip()
        parsed_dates = {}
        for name, value, lookup in (
            ("date_from", date_from, "received_at__date__gte"),
            ("date_to", date_to, "received_at__date__lte"),
        ):
            if value:
                try:
                    parsed_dates[name] = date.fromisoformat(value)
                except ValueError:
                    raise ValidationError({name: "Use YYYY-MM-DD."})
                queryset = queryset.filter(**{lookup: parsed_dates[name]})
        if len(parsed_dates) == 2 and parsed_dates["date_from"] > parsed_dates["date_to"]:
            raise ValidationError({"date_to": "End date must be on or after start date."})

        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(invoice__invoice_number__icontains=search)
                | Q(invoice__customer_snapshot__name__icontains=search)
                | Q(invoice__subscription__customer__name__icontains=search)
                | Q(reference__icontains=search)
            )

        paginator = CatalogPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([{
            "id": str(payment.pk),
            "invoice_id": str(payment.invoice_id),
            "invoice_number": payment.invoice.invoice_number,
            "customer_name": (
                payment.invoice.customer_snapshot.get("name")
                or payment.invoice.subscription.customer.name
            ),
            "amount": str(payment.amount),
            "currency": payment.currency,
            "method": payment.method,
            "payment_date": payment.received_at.date().isoformat(),
            "received_at": payment.received_at.isoformat(),
            "reference": payment.reference,
            "note": payment.note,
        } for payment in page])
