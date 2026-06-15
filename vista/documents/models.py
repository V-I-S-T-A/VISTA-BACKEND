import uuid
from django.db import models
from submissions.models import Submission

class Document(models.Model):
    document_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission_id = models.ForeignKey(Submission, on_delete=models.CASCADE, db_column="submission_id")
    file_name = models.CharField(max_length=255)
    file_url = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=100)
    file_size_kb = models.IntegerField()
    version = models.IntegerField()
    is_current = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Documents"