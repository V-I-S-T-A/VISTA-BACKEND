import uuid
from django.db import models


class DocumentType(models.Model):
    doc_type_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, db_index=True)
    code = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Machine-readable form code (e.g. 'FM-USTP-OSA-04B') used to match "
                  "OCR-identified templates to this document type. Leave blank if this "
                  "document type has no standardized scannable form.",
    )

    description = models.TextField()
    required_fields = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "tbl_Document_types"
        indexes = [
            models.Index(fields=["is_active", "name"], name="doctype_active_name_idx"),
        ]
        ordering = ["name"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper() if self.code else None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name