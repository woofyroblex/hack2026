from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0006_invoice_cancellation_reason"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(fields=("currency", "status", "confirmed_at"), name="inv_cur_stat_conf_idx"),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(fields=("currency", "status", "due_date"), name="inv_cur_stat_due_idx"),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(fields=("customer_id_snapshot", "status"), name="inv_cust_stat_idx"),
        ),
    ]
