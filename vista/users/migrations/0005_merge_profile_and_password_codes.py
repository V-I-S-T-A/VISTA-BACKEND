from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_use_plaintext_password_codes"),
        ("users", "0004_user_birth_date_gender"),
    ]

    operations = []
