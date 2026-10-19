from django.db import migrations, models


def use_code_column(apps, schema_editor):
    PasswordChangeCode = apps.get_model("users", "PasswordChangeCode")
    table_name = PasswordChangeCode._meta.db_table
    connection = schema_editor.connection
    quote = connection.ops.quote_name

    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return
        columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

    table = quote(table_name)
    if "code" not in columns:
        code_field = models.CharField(max_length=6, null=True)
        code_field.set_attributes_from_name("code")
        code_field.model = PasswordChangeCode
        schema_editor.add_field(PasswordChangeCode, code_field)

        # Hashed codes cannot be converted back to the emailed six-digit code.
        # They are short-lived, so invalidate them rather than storing unusable
        # placeholder values in the new plaintext-code column.
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table}")
            schema_editor.execute(
                f"ALTER TABLE {table} ALTER COLUMN {quote('code')} SET NOT NULL"
            )

    with connection.cursor() as cursor:
        current_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

    for obsolete_column in ("code_hash", "attempts"):
        if obsolete_column in current_columns:
            schema_editor.execute(
                f"ALTER TABLE {table} DROP COLUMN {quote(obsolete_column)}"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_user_must_change_password"),
    ]

    operations = [
        migrations.RunPython(use_code_column),
    ]
