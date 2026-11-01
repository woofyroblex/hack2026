"""Staff invoice operations and customer-scoped read-only invoice access."""

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import EmailOutbox
from notifications.services import EmailQueueError, queue_email
from payments.services import InvalidPayment, PaymentConflict, record_payment
from .models import DocumentJob, Invoice, InvoiceStatus
from .serializers import serialize_invoice
from .services.documents import document_key, queue_invoice_pdf
from .services.status import InvalidInvoiceTransition, transition_invoice_status


def invoice_queryset(request, *, portal=False):
    queryset = Invoice.objects.select_related("subscription__customer").prefetch_related("lines", "payments")
    if portal:
        try:
            customer = request.user.customer_profile
        except (AttributeError, ObjectDoesNotExist):
            return queryset.none()
        return queryset.filter(
            Q(customer_id_snapshot=customer.pk)
            | Q(customer_id_snapshot__isnull=True, subscription__customer=customer),
            status__in=(InvoiceStatus.CONFIRMED, InvoiceStatus.PAID),
        )
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Authorized staff access is required.")
    return queryset


def get_invoice(request, pk, *, portal=False):
    try:
        return invoice_queryset(request, portal=portal).get(pk=pk)
    except Invoice.DoesNotExist:
        raise NotFound("Invoice not found.")


class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated]
    portal = False

    def get(self, request):
        queryset = invoice_queryset(request, portal=self.portal)
        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(status__iexact=status_filter)
        currency = request.query_params.get("currency", "").strip()
        if currency:
            queryset = queryset.filter(currency=currency.upper())
        customer_id = request.query_params.get("customer_id")
        if customer_id:
            try:
                customer_id = int(customer_id)
            except (ValueError, TypeError):
                raise ValidationError({"customer_id": "Expected a customer ID."})
            queryset = queryset.filter(
                Q(customer_id_snapshot=customer_id)
                | Q(customer_id_snapshot__isnull=True, subscription__customer_id=customer_id),
            )
        subscription_id = request.query_params.get("subscription_id")
        if subscription_id:
            try:
                queryset = queryset.filter(subscription_id=serializers.UUIDField().run_validation(subscription_id))
            except serializers.ValidationError:
                raise ValidationError({"subscription_id": "Expected a subscription UUID."})
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(invoice_number__icontains=search) | Q(subscription__customer__name__icontains=search))
        if request.query_params.get("overdue") == "true":
            queryset = queryset.filter(status=InvoiceStatus.CONFIRMED, due_date__lt=timezone.localdate())
        paginator = PageNumberPagination()
        paginator.page_size = 25
        paginator.page_size_query_param = "page_size"
        paginator.max_page_size = 100
        page = paginator.paginate_queryset(queryset.order_by("-created_at", "-id"), request, view=self)
        return paginator.get_paginated_response([serialize_invoice(invoice, portal=self.portal) for invoice in page])


class InvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated]
    portal = False

    def get(self, request, pk):
        return Response(serialize_invoice(get_invoice(request, pk, portal=self.portal), portal=self.portal))


class InvoiceTransitionView(APIView):
    permission_classes = [IsAuthenticated]
    target_status = None

    def post(self, request, pk):
        invoice = get_invoice(request, pk)
        try:
            transition_invoice_status(invoice.pk, self.target_status, reason=request.data.get("reason", ""))
        except InvalidInvoiceTransition as exc:
            raise ValidationError({"status": str(exc)})
        return Response(serialize_invoice(get_invoice(request, pk)))


class PaymentInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.CharField(max_length=40)
    payment_date = serializers.DateField()
    reference = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=128)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class InvoicePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        invoice = get_invoice(request, pk)
        payload = request.data.copy()
        if not payload.get("idempotency_key"):
            payload["idempotency_key"] = request.headers.get("Idempotency-Key", "")
        data = PaymentInput(data=payload)
        data.is_valid(raise_exception=True)
        try:
            result = record_payment(invoice.pk, **data.validated_data)
        except PaymentConflict as exc:
            return Response({"code": "PAYMENT_CONFLICT", "message": str(exc), "fields": {}}, status=409)
        except InvalidPayment as exc:
            raise ValidationError({"payment": str(exc)})
        payload = serialize_invoice(get_invoice(request, pk))
        payload.update(payment_id=str(result.payment.pk), payment_created=result.created)
        return Response(payload, status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK)


def serialize_job(job, request, *, portal=False):
    prefix = "portal/" if portal else ""
    return {
        "id": str(job.pk), "invoice_id": str(job.invoice_id), "status": job.status,
        "attempts": job.attempts,
        "message": "Invoice PDF generation failed. Ask staff to retry." if job.status == DocumentJob.Status.FAILED else "",
        "download_url": request.build_absolute_uri(f"/api/v1/{prefix}invoices/{job.invoice_id}/pdf/"),
    }


class InvoicePDFView(APIView):
    permission_classes = [IsAuthenticated]
    portal = False

    def get(self, request, pk):
        invoice = get_invoice(request, pk, portal=self.portal)
        job = DocumentJob.objects.filter(dedupe_key=document_key(invoice)).first()
        if job is None:
            return Response({
                "code": "DOCUMENT_NOT_REQUESTED",
                "message": "Request PDF generation before checking its status.",
                "fields": {},
            }, status=404)
        if job.status == DocumentJob.Status.SUCCEEDED:
            try:
                document = default_storage.open(job.storage_key, "rb")
            except (OSError, ValueError):
                return Response({"code": "DOCUMENT_UNAVAILABLE", "message": "The stored PDF is unavailable. Ask staff to regenerate it.", "fields": {}}, status=503)
            return FileResponse(document, as_attachment=True, filename=f"{invoice.invoice_number}.pdf", content_type="application/pdf")
        return Response(serialize_job(job, request, portal=self.portal), status=503 if job.status == DocumentJob.Status.FAILED else 202)

    def post(self, request, pk):
        invoice = get_invoice(request, pk, portal=self.portal)
        job = queue_invoice_pdf(invoice, retry_failed=True)
        if job.status == DocumentJob.Status.SUCCEEDED and not default_storage.exists(job.storage_key):
            DocumentJob.objects.filter(pk=job.pk).update(status=DocumentJob.Status.FAILED)
            job = queue_invoice_pdf(invoice, retry_failed=True)
        return Response(serialize_job(job, request, portal=self.portal), status=202 if job.status != DocumentJob.Status.SUCCEEDED else 200)


class PortalInvoicePDFView(InvoicePDFView):
    portal = True


class DocumentJobView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            job = DocumentJob.objects.select_related("invoice").get(pk=pk)
        except DocumentJob.DoesNotExist:
            raise NotFound("Job not found.")
        portal = not (request.user.is_staff or request.user.is_superuser)
        get_invoice(request, job.invoice_id, portal=portal)
        result = serialize_job(job, request, portal=portal)
        return Response(result)


class InvoiceSendView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        invoice = get_invoice(request, pk)
        if invoice.status not in (InvoiceStatus.CONFIRMED, InvoiceStatus.PAID):
            raise ValidationError({"status": "Only confirmed or paid invoices can be sent."})
        data = serialize_invoice(invoice)
        job = queue_invoice_pdf(invoice, retry_failed=True)
        try:
            result = queue_email(
                "invoice_document", data["customer_email"],
                {"invoice_id": str(invoice.pk), "invoice_number": invoice.invoice_number,
                 "document_job_id": str(job.pk), "customer_name": data["customer_name"],
                 "total": data["total"], "currency": invoice.currency},
                f"invoice:{invoice.pk}:document:{job.pk}:{data['customer_email']}",
            )
        except (ValueError, DjangoValidationError, EmailQueueError) as exc:
            raise ValidationError({"email": str(exc)})
        email = EmailOutbox.objects.get(pk=result.email_id)
        return Response({"email_id": str(email.pk), "status": email.status, "recipient": email.recipient}, status=202)
