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
    version = models.IntegerField(default=1)
    is_current = models.BooleanField(default=True, db_index=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Documents"
        indexes = [
            models.Index(fields=["submission_id", "is_current"], name="doc_submission_current_idx"),
            models.Index(fields=["-uploaded_at"], name="doc_uploaded_at_idx"),
        ]
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.file_name} (v{self.version})"