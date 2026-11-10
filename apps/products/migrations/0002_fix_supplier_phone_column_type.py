from django.db import migrations, models


def fix_supplier_text_column_types(apps, schema_editor):
    supplier_model = apps.get_model("products", "Supplier")
    connection = schema_editor.connection
    fields = [
        supplier_model._meta.get_field("document_number"),
        supplier_model._meta.get_field("phone"),
    ]

    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(
            cursor, supplier_model._meta.db_table
        )
        constraints = connection.introspection.get_constraints(
            cursor, supplier_model._meta.db_table
        )

    field_types = {}
    for field in fields:
        column = next(column for column in columns if column.name == field.column)
        field_type = connection.introspection.get_field_type(
            column.type_code, column
        )
        if field_type == "CharField":
            continue
        if field_type not in {"IntegerField", "BigIntegerField"}:
            raise RuntimeError(
                f"Cannot safely convert supplier.{field.name} "
                f"from {field_type} to CharField."
            )
        field_types[field.name] = field_type

    for name, constraint in constraints.items():
        if constraint.get("check") and set(constraint["columns"]) & set(
            field_types
        ):
            if connection.vendor != "postgresql":
                raise RuntimeError(
                    "Cannot safely remove supplier check constraints "
                    "on a non-PostgreSQL database."
                )
            table = connection.ops.quote_name(supplier_model._meta.db_table)
            constraint_name = connection.ops.quote_name(name)
            schema_editor.execute(
                f"ALTER TABLE {table} DROP CONSTRAINT {constraint_name}"
            )

    for field in fields:
        field_type = field_types.get(field.name)
        if field_type is None:
            continue
        old_field_class = {
            "IntegerField": models.IntegerField,
            "BigIntegerField": models.BigIntegerField,
        }[field_type]
        old_field = old_field_class(blank=True)
        old_field.set_attributes_from_name(field.name)
        old_field.model = supplier_model
        schema_editor.alter_field(
            supplier_model, old_field, field, strict=False
        )


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(fix_supplier_text_column_types),
    ]
