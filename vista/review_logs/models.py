import uuid
from django.db import models
from submissions.models import Submission
from users.models import User

class ReviewLog(models.Model):
    log_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission_id = models.ForeignKey(Submission, on_delete=models.CASCADE, db_column="submission_id")
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column="changed_by")
    remarks_text = models.TextField()
    old_status = models.CharField(max_length=100)
    new_status = models.CharField(max_length=100)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Review_Logs"