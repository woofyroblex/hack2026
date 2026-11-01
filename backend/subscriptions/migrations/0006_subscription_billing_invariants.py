from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0005_alter_subscriptionline_options_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.CheckConstraint(
                check=models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=models.F("start_date")),
                name="subscription_expiry_after_start_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.CheckConstraint(
                check=models.Q(subtotal__gte=0, discount_total__gte=0, tax_total__gte=0, total__gte=0),
                name="subscription_totals_nonneg_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.CheckConstraint(
                check=models.Q(discount_total__lte=models.F("subtotal")),
                name="subscription_discount_lte_subtotal_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.CheckConstraint(
                check=(models.Q(billing_anchor_day__isnull=True)
                       | models.Q(billing_anchor_day__gte=1, billing_anchor_day__lte=31)),
                name="subscription_anchor_day_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.CheckConstraint(
                check=(models.Q(billing_anchor_month__isnull=True)
                       | models.Q(billing_anchor_month__gte=1, billing_anchor_month__lte=12)),
                name="subscription_anchor_month_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscriptionline",
            constraint=models.CheckConstraint(
                check=models.Q(
                    unit_price__gte=0, gross_amount__gte=0, discount_amount__gte=0,
                    net_amount__gte=0, tax_amount__gte=0,
                ),
                name="subscription_line_amounts_nonneg_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="subscriptionline",
            constraint=models.CheckConstraint(
                check=models.Q(discount_amount__lte=models.F("gross_amount")),
                name="subscription_line_discount_lte_gross_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="billingattempt",
            constraint=models.CheckConstraint(
                check=models.Q(period_end__gt=models.F("period_start")),
                name="billing_attempt_period_valid_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="billingattempt",
            constraint=models.CheckConstraint(
                check=(models.Q(result="SUCCEEDED", invoice_id__isnull=False)
                       | (~models.Q(result="SUCCEEDED") & models.Q(invoice_id__isnull=True))),
                name="billing_attempt_invoice_state_ck",
            ),
        ),
    ]
