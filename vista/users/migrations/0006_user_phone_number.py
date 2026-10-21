from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0005_merge_profile_and_password_codes")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone_number",
            field=models.CharField(blank=True, default="", max_length=13),
        ),
    ]
