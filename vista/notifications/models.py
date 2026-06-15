import uuid
from django.db import models
from users.models import User
from submissions.models import Submission

class Notification(models.Model):
    notification_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column="user_id")
    submission_id = models.ForeignKey(Submission, on_delete=models.CASCADE, db_column="submission_id")
    type = models.CharField(max_length=100)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Notifications"