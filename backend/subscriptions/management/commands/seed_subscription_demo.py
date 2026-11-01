from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from customers.models import Customer
from plans.models import PaymentTerm, Plan
from products.models import Product, ProductVariant, TaxRule
from products.services.catalog_adapter import calculate_price
from quotations.models import QuoteTemplate, TemplateLine
from subscriptions.models import Subscription, SubscriptionEvent, SubscriptionLine


class Command(BaseCommand):
    help = 'Create the demo catalog and one active subscription due for recurring billing.'

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        customer, _ = Customer.objects.update_or_create(
            email='demo-customer@example.test',
            defaults={
                'name': 'Jordan Lee',
                'company': 'Northstar Demo Studio',
                'phone': '+91 90000 12345',
                'billing_address': '42 Example Street, Bengaluru, Karnataka',
            },
        )
        plan, _ = Plan.objects.update_or_create(
            name='Demo Monthly Plan',
            defaults={
                'base_price': Decimal('9999.00'),
                'billing_cadence': Plan.Cadence.MONTHLY,
                'minimum_quantity': 1,
                'availability_start_date': today,
                'allow_pause': True,
                'allow_early_closure': True,
                'allow_renewal': True,
                'auto_close': False,
                'is_active': True,
            },
        )
        payment_term, _ = PaymentTerm.objects.update_or_create(
            name='Demo Net 15',
            defaults={'days_until_due': 15, 'is_active': True},
        )
        plan.payment_term = payment_term
        plan.save(update_fields=['payment_term', 'updated_at'])
        product, _ = Product.objects.update_or_create(
            name='Demo Workspace License',
            defaults={
                'type': Product.Type.SERVICE,
                'sales_price': Decimal('1500.00'),
                'cost_price': Decimal('500.00'),
                'notes': 'Sample catalog item for subscription workflow demos.',
                'is_active': True,
            },
        )
        variant, _ = ProductVariant.objects.update_or_create(
            product=product,
            attribute_label='Edition',
            option_value='Pro',
            defaults={'price_adjustment': Decimal('500.00'), 'is_active': True},
        )
        tax, _ = TaxRule.objects.update_or_create(
            name='Demo Tax 18%',
            defaults={'percentage_rate': Decimal('18.00'), 'is_active': True},
        )
        product.taxes.set([tax])
        plan.taxes.set([tax])
        template, _ = QuoteTemplate.objects.update_or_create(
            name='Demo Subscription Quote',
            defaults={
                'plan': plan,
                'validity_days': 14,
                'payment_term': payment_term,
                'is_active': True,
            },
        )
        template_line, _ = TemplateLine.objects.update_or_create(
            template=template,
            product=product,
            variant=variant,
            defaults={'quantity': 1, 'position': 0},
        )
        template_line.taxes.set([tax])

        # The date in this number makes seeding idempotent without resetting a
        # billing cursor after an invoice has already been created.
        subscription_number = f'SUB-DEMO-{today:%Y%m%d}'
        subscription = Subscription.objects.filter(number=subscription_number).first()
        if subscription is None:
            requested_lines = [{
                'product_id': product.pk,
                'variant_id': variant.pk,
                'quantity': 1,
            }]
            pricing = calculate_price(plan=plan, lines=requested_lines, effective_date=today)
            plan_tax_rate = sum(
                (rule.percentage_rate for rule in plan.taxes.filter(is_active=True)),
                Decimal('0.00'),
            )
            subscription = Subscription.objects.create(
                number=subscription_number,
                customer=customer,
                plan=plan,
                template=template,
                status=Subscription.Status.ACTIVE,
                cadence=plan.billing_cadence,
                start_date=today,
                payment_term_days=payment_term.days_until_due,
                currency=pricing.get('currency', 'INR'),
                base_price_snapshot=plan.base_price,
                plan_base_price_snapshot=plan.base_price,
                plan_tax_rate_snapshot=plan_tax_rate,
                subtotal=Decimal(str(pricing['subtotal'])),
                discount_total=Decimal(str(pricing['total_discount'])),
                tax_total=Decimal(str(pricing['total_tax'])),
                total=Decimal(str(pricing['final_total'])),
                minimum_quantity_snapshot=plan.minimum_quantity,
                allow_pause_snapshot=plan.allow_pause,
                allow_early_close_snapshot=plan.allow_early_closure,
                allow_renewal_snapshot=plan.allow_renewal,
                auto_close_on_expiry_snapshot=plan.auto_close,
                billing_anchor_day=today.day,
                billing_anchor_month=today.month,
                next_billing_date=today,
            )
            priced = pricing['lines'][0]
            line = SubscriptionLine.objects.create(
                subscription=subscription,
                product=product,
                variant=variant,
                quantity=1,
                product_name_snapshot=product.name,
                variant_name_snapshot=f'{variant.attribute_label}: {variant.option_value}',
                unit_sales_price=Decimal(str(priced['unit_sales_price'])),
                variant_adjustment=Decimal(str(priced['variant_adjustment'])),
                effective_unit_price=Decimal(str(priced['effective_unit_price'])),
                line_subtotal=Decimal(str(priced['line_subtotal'])),
                discount_amount=Decimal(str(priced['discount_amount'])),
                line_net_amount=Decimal(str(priced['line_net_amount'])),
                tax_rate=Decimal(str(priced['tax_rate'])),
                tax_amount=Decimal(str(priced['tax_amount'])),
                final_line_total=Decimal(str(priced['final_line_total'])),
                unit_price=Decimal(str(priced['effective_unit_price'])),
                gross_amount=Decimal(str(priced['line_subtotal'])),
                net_amount=Decimal(str(priced['line_net_amount'])),
                tax_rate_snapshot=Decimal(str(priced['tax_rate'])),
                sort_order=0,
            )
            line.taxes.set([tax])
            SubscriptionEvent.objects.create(
                subscription=subscription,
                action='seeded_demo',
                to_status=Subscription.Status.ACTIVE,
                effective_on=today,
                reason='Repeatable demonstration subscription.',
            )
        self.stdout.write(self.style.SUCCESS('Demo subscription records are ready:'))
        self.stdout.write(f'  customer_id={customer.pk} ({customer.name})')
        self.stdout.write(f'  plan_id={plan.pk} ({plan.name})')
        self.stdout.write(f'  product_id={product.pk} ({product.name})')
        self.stdout.write(f'  variant_id={variant.pk} ({variant.attribute_label}: {variant.option_value})')
        self.stdout.write(f'  template_id={template.pk} ({template.name})')
        self.stdout.write(f'  subscription_id={subscription.pk} ({subscription.number})')
        self.stdout.write(f'  next_billing_date={subscription.next_billing_date}')
