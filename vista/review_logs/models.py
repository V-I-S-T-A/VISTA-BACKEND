import uuid
from django.db import models
from submissions.models import Submission
from users.models import User


class ReviewLog(models.Model):
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission_id = models.ForeignKey(Submission, on_delete=models.CASCADE, db_column="submission_id")
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column="changed_by")
    remarks_text = models.TextField(blank=True)
    old_status = models.CharField(max_length=50)
    new_status = models.CharField(max_length=50)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Review_Logs"
        indexes = [
            models.Index(fields=["submission_id", "-changed_at"], name="rlog_submission_date_idx"),
            models.Index(fields=["-changed_at"], name="rlog_changed_at_idx"),
        ]
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.submission_id_id}: {self.old_status} -> {self.new_status}"