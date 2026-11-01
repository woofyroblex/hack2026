from datetime import date, timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.models import DocumentJob, Invoice, InvoiceLine, InvoiceStatus
from customers.models import Customer
from notifications.models import EmailOutbox
from payments.models import Payment
from plans.models import Plan
from subscriptions.models import Subscription


class InvoiceAPITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(username="invoice-staff", is_staff=True)
        self.owner = User.objects.create_user(username="invoice-owner")
        self.stranger = User.objects.create_user(username="invoice-stranger")
        self.customer = Customer.objects.create(user=self.owner, name="Invoice Customer", email="invoice@example.com")
        self.other_customer = Customer.objects.create(user=self.stranger, name="Other", email="other@example.com")
        self.plan = Plan.objects.create(name="Invoice plan", base_price=Decimal("100.00"))
        self.subscription = Subscription.objects.create(
            customer=self.customer, plan=self.plan, start_date=date(2026, 1, 1), payment_term_days=7,
        )
        self.invoice = Invoice.objects.create(
            invoice_number="INV-API-1", subscription=self.subscription,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            customer_id_snapshot=self.customer.pk,
            customer_snapshot={"name": self.customer.name, "email": self.customer.email},
            subtotal=Decimal("100.00"), tax_total=Decimal("18.00"), total=Decimal("118.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice, line_number=1, description="Monthly service", quantity=1,
            unit_price=100, gross_amount=100, taxable_amount=100, tax_rate=18, tax_amount=18, total_amount=118,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.staff)
        self.url = f"/api/v1/invoices/{self.invoice.pk}/"

    def confirm(self):
        response = self.client.post(self.url + "confirm/", {}, format="json")
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response

    def payment(self, amount="40.00", key="payment-one", **extra):
        return self.client.post(self.url + "payments/", {
            "amount": amount, "method": "bank_transfer", "payment_date": timezone.localdate().isoformat(),
            "reference": "BANK-123", "idempotency_key": key, **extra,
        }, format="json")

    def test_staff_list_detail_and_confirm_preserve_decimal_totals(self):
        listing = self.client.get("/api/v1/invoices/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        response = self.confirm()
        self.assertEqual(response.data["total"], "118.00")
        self.assertEqual(response.data["balance"], "118.00")
        self.assertEqual(response.data["amount_paid"], "0.00")
        self.assertEqual(response.data["lines"][0]["total_amount"], "118.00")
        self.assertEqual(response.data["due_date"], (timezone.localdate() + timedelta(days=7)).isoformat())
        self.assertEqual(self.confirm().data["confirmed_at"], response.data["confirmed_at"])

    def test_customer_cannot_read_staff_routes_or_mutate_invoices(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/invoices/").status_code, 403)
        for action in ("confirm", "cancel", "payments", "send", "pdf"):
            self.assertEqual(self.client.post(self.url + action + "/", {}, format="json").status_code, 403)

    def test_portal_hides_drafts_and_other_customer_invoices(self):
        portal_url = self.url.replace("/invoices/", "/portal/invoices/")
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(portal_url).status_code, 404)
        self.client.force_authenticate(self.staff)
        self.confirm()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get("/api/v1/portal/invoices/").data["count"], 1)
        self.assertEqual(self.client.get(portal_url).status_code, 200)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get("/api/v1/portal/invoices/").data["count"], 0)
        self.assertEqual(self.client.get(portal_url).status_code, 404)
        self.assertEqual(self.client.get(portal_url + "pdf/").status_code, 404)

    def test_partial_payment_retry_and_settlement(self):
        self.confirm()
        first = self.payment()
        self.assertEqual(first.status_code, 201, getattr(first, "data", None))
        self.assertEqual(first.data["balance"], "78.00")
        self.assertEqual(first.data["status"], "Confirmed")
        retry = self.payment()
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data["payment_id"], first.data["payment_id"])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(self.payment("41.00").status_code, 409)
        self.assertEqual(self.payment("78.01", "too-much").status_code, 400)
        paid = self.payment("78.00", "final-payment")
        self.assertEqual(paid.status_code, 201)
        self.assertEqual(paid.data["status"], "Paid")
        self.assertEqual(paid.data["balance"], "0.00")
        self.assertEqual(paid.data["amount_paid"], "118.00")
        self.assertEqual(self.payment("78.00", "final-payment").status_code, 200)
        self.assertEqual(self.payment("0.01", "extra-payment").status_code, 400)

    def test_payment_and_cancellation_state_guards(self):
        self.assertEqual(self.payment().status_code, 400)
        self.confirm()
        self.payment()
        self.assertEqual(self.client.post(self.url + "cancel/", {}, format="json").status_code, 400)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.CONFIRMED)

    def test_cancel_is_idempotent_and_cannot_be_confirmed_or_paid(self):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url + "cancel/", {"reason": "Customer request"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.url + "confirm/", {}, format="json").status_code, 400)
        self.assertEqual(self.payment().status_code, 400)

    def test_invalid_amounts_dates_and_missing_idempotency_key(self):
        self.confirm()
        for amount in ("0", "-1", "NaN", "Infinity", "1.001", "10000000000.00"):
            with self.subTest(amount=amount):
                self.assertEqual(self.payment(amount).status_code, 400)
        self.assertEqual(self.payment(key="").status_code, 400)
        self.assertEqual(self.payment(payment_date="invalid").status_code, 400)
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertEqual(self.payment(payment_date=tomorrow).status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_confirmation_rejects_unreconciled_lines(self):
        Invoice.objects.filter(pk=self.invoice.pk).update(total=Decimal("117.00"))
        self.assertEqual(self.client.post(self.url + "confirm/", {}, format="json").status_code, 400)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_pdf_job_download_and_email_attachment_are_real_and_idempotent(self):
        from billing.tasks import render_invoice_pdf
        from notifications.tasks import deliver_email

        self.confirm()
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            with patch("billing.tasks.render_invoice_pdf.delay") as dispatch:
                with self.captureOnCommitCallbacks(execute=True):
                    queued = self.client.post(self.url + "pdf/", {}, format="json")
            self.assertEqual(queued.status_code, 202)
            dispatch.assert_called_once()
            self.assertEqual(self.client.get(self.url + "pdf/").status_code, 202)
            self.assertEqual(render_invoice_pdf.run(queued.data["id"]), "succeeded")
            self.assertEqual(render_invoice_pdf.run(queued.data["id"]), "already_succeeded")
            document = self.client.get(self.url + "pdf/")
            self.assertEqual(document.status_code, 200)
            content = b"".join(document.streaming_content)
            self.assertTrue(content.startswith(b"%PDF"))
            self.assertGreater(len(content), 2000)
            self.client.force_authenticate(self.owner)
            portal_pdf = self.client.get(self.url.replace("/invoices/", "/portal/invoices/") + "pdf/")
            self.assertEqual(portal_pdf.status_code, 200)
            self.client.force_authenticate(self.staff)
            with patch("notifications.tasks.deliver_email.delay") as dispatch:
                with self.captureOnCommitCallbacks(execute=True):
                    sent = self.client.post(self.url + "send/", {}, format="json")
                    retry = self.client.post(self.url + "send/", {}, format="json")
            self.assertEqual(sent.status_code, 202)
            self.assertEqual(sent.data["email_id"], retry.data["email_id"])
            dispatch.assert_called_once()
            self.assertEqual(EmailOutbox.objects.count(), 1)
            self.assertEqual(deliver_email.run(sent.data["email_id"]), "sent")
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].attachments[0][2], "application/pdf")
            self.assertTrue(mail.outbox[0].attachments[0][1].startswith(b"%PDF"))
            self.assertEqual(DocumentJob.objects.count(), 1)
