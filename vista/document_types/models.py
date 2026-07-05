import uuid
from django.db import models


class DocumentType(models.Model):
    doc_type_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    description = models.TextField()
    required_fields = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "tbl_Document_types"
        indexes = [
            models.Index(fields=["is_active", "name"], name="doctype_active_name_idx"),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name