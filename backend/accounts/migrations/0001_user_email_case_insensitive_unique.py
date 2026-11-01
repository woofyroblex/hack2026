from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower
from django.db.models import Count


CONSTRAINT = models.UniqueConstraint(
    Lower("email"),
    condition=~models.Q(email=""),
    name="user_email_ci_unique",
)


def add_case_insensitive_email_constraint(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    alias = schema_editor.connection.alias
    duplicates = (
        User.objects.using(alias)
        .exclude(email="")
        .annotate(normalized_email=Lower("email"))
        .values("normalized_email")
        .annotate(row_count=Count("pk"))
        .filter(row_count__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError(
            "Cannot enforce case-insensitive account email uniqueness while duplicate email addresses exist. "
            "Resolve the account records without deleting user data, then rerun migrations."
        )
    schema_editor.add_constraint(User, CONSTRAINT)


def remove_case_insensitive_email_constraint(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    schema_editor.remove_constraint(User, CONSTRAINT)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            add_case_insensitive_email_constraint,
            remove_case_insensitive_email_constraint,
        ),
    ]
