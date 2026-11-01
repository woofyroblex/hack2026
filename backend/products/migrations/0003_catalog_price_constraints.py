from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_alter_product_options_alter_taxrule_options_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="taxrule",
            constraint=models.CheckConstraint(
                check=models.Q(percentage_rate__gte=0, percentage_rate__lte=100),
                name="tax_rate_range_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                check=models.Q(sales_price__gte=0),
                name="product_sales_price_nonneg_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                check=models.Q(cost_price__gte=0),
                name="product_cost_price_nonneg_ck",
            ),
        ),
    ]
