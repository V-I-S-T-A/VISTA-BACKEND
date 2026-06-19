import uuid
from django.db import models


class Organization(models.Model):
    org_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    acronym = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Organizations"
        indexes = [
            models.Index(fields=["is_active", "name"], name="org_active_name_idx"),
            models.Index(fields=["-created_at"], name="org_created_at_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.acronym