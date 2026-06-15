import uuid
from django.db import models

class DocumentType(models.Model):
    doc_type_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField()
    required_fields = models.JSONField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "tbl_Document_types"