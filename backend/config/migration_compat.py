"""Compatibility operations for the independently authored migration branches.

The original migration names remain valid for databases that applied either
branch. Only missing tables/columns are added when the other branch is replayed.
"""
from django.db import migrations, models
from django.utils import timezone


def columns(schema_editor, model):
    with schema_editor.connection.cursor() as cursor:
        return {column.name for column in schema_editor.connection.introspection.get_table_description(cursor, model._meta.db_table)}


def add_missing_field(schema_editor, model, field):
    if field.many_to_many:
        if field.remote_field.through._meta.db_table not in schema_editor.connection.introspection.table_names():
            schema_editor.add_field(model, field)
        return
    if field.column in columns(schema_editor, model):
        return
    if field.name == 'number':
        temporary = field.clone()
        temporary.set_attributes_from_name(field.name)
        temporary.model = model
        temporary.null = True
        temporary._unique = False
        schema_editor.add_field(model, temporary)
        for record in model.objects.using(schema_editor.connection.alias).only('id').iterator():
            model.objects.using(schema_editor.connection.alias).filter(pk=record.pk).update(number=f'SUB-{str(record.pk).replace("-", "")[:12].upper()}')
        schema_editor.alter_field(model, temporary, field)
        return
    if not field.null and not field.has_default() and isinstance(field, models.DecimalField):
        field_name = field.name
        field = field.clone()
        field.set_attributes_from_name(field_name)
        field.model = model
        field.default = 0
    schema_editor.add_field(model, field)


class CreateModel(migrations.CreateModel):
    def state_forwards(self, app_label, state):
        key = (app_label, self.name_lower)
        if key not in state.models:
            return super().state_forwards(app_label, state)
        for name, field in self.fields:
            if name not in state.models[key].fields:
                state.add_field(app_label, self.name_lower, name, field, preserve_default=True)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.name)
        if model._meta.db_table not in schema_editor.connection.introspection.table_names():
            return super().database_forwards(app_label, schema_editor, from_state, to_state)
        for name, _field in self.fields:
            add_missing_field(schema_editor, model, model._meta.get_field(name))


class AddField(migrations.AddField):
    def state_forwards(self, app_label, state):
        fields = state.models[(app_label, self.model_name_lower)].fields
        # These two fields represent the same existing database column.
        if self.model_name_lower == 'subscription' and self.name == 'customer_id' and 'customer' in fields:
            return
        if self.model_name_lower == 'subscription' and self.name == 'customer' and 'customer_id' in fields:
            state.remove_field(app_label, self.model_name_lower, 'customer_id')
        if self.name not in fields:
            super().state_forwards(app_label, state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.name == 'customer_id' and 'customer' in to_state.models[(app_label, self.model_name_lower)].fields:
            return
        add_missing_field(schema_editor, model, model._meta.get_field(self.name))


class RemoveConstraint(migrations.RemoveConstraint):
    def state_forwards(self, app_label, state):
        constraints = state.models[(app_label, self.model_name_lower)].options.get('constraints', [])
        if any(constraint.name == self.name for constraint in constraints):
            super().state_forwards(app_label, state)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(cursor, model._meta.db_table)
        if self.name in constraints:
            super().database_forwards(app_label, schema_editor, from_state, to_state)


class AddConstraint(migrations.AddConstraint):
    """Add a constraint only when it is absent from a legacy schema."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        with schema_editor.connection.cursor() as cursor:
            constraints = schema_editor.connection.introspection.get_constraints(cursor, model._meta.db_table)
        existing = constraints.get(self.constraint.name)
        if existing is None:
            return super().database_forwards(app_label, schema_editor, from_state, to_state)

        expected_columns = [model._meta.get_field(name).column for name in self.constraint.fields]
        if not existing.get("unique") or existing.get("columns") != expected_columns:
            raise RuntimeError(f"Existing constraint {self.constraint.name!r} does not match the migration definition.")
