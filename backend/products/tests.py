from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from plans.models import Plan
from products.models import Product, ProductVariant, TaxRule
from products.services import calculate_price


class CatalogPricingTests(TestCase):
    def test_plan_product_variant_and_tax_totals_are_server_calculated(self):
        plan_tax = TaxRule.objects.create(name="Plan tax", percentage_rate=Decimal("5.00"))
        product_tax = TaxRule.objects.create(name="Product tax", percentage_rate=Decimal("18.00"))
        plan = Plan.objects.create(name="Starter", base_price=Decimal("100.00"))
        plan.taxes.add(plan_tax)
        product = Product.objects.create(name="Support", sales_price=Decimal("50.00"))
        product.taxes.add(product_tax)
        variant = ProductVariant.objects.create(
            product=product,
            attribute_label="Tier",
            option_value="Priority",
            price_adjustment=Decimal("10.00"),
        )

        result = calculate_price(
            plan=plan,
            lines=[{"product_id": product.pk, "variant_id": variant.pk, "quantity": 2}],
            effective_date=date(2026, 10, 31),
        )

        self.assertEqual(result["subtotal"], Decimal("220.00"))
        self.assertEqual(result["total_tax"], Decimal("26.60"))
        self.assertEqual(result["final_total"], Decimal("246.60"))
        self.assertEqual(result["lines"][0]["effective_unit_price"], Decimal("60.00"))
        self.assertEqual(result["lines"][0]["final_line_total"], Decimal("141.60"))

    def test_variant_must_belong_to_submitted_product(self):
        first = Product.objects.create(name="First")
        second = Product.objects.create(name="Second")
        variant = ProductVariant.objects.create(product=first, attribute_label="Size", option_value="Large")
        plan = Plan.objects.create(name="Starter")

        with self.assertRaises(ValidationError):
            calculate_price(
                plan=plan,
                lines=[{"product_id": second.pk, "variant_id": variant.pk, "quantity": 1}],
                effective_date=date(2026, 10, 31),
            )
