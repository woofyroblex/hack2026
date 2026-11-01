from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=("currency", "received_at"), name="pay_cur_received_idx"),
        ),
    ]
