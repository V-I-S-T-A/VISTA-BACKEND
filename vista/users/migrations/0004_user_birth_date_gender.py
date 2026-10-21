from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0003_user_must_change_password")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="birth_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="gender",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
