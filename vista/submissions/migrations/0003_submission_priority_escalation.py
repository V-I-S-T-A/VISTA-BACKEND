from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("submissions", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="submission",
            name="priority_escalation",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
