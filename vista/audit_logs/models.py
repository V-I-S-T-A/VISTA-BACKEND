import uuid
from django.db import models
from users.models import User


class AuditLog(models.Model):
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_STATUS_CHANGE = "status_change"

    ACTION_CHOICES = (
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
        (ACTION_LOGIN, "Login"),
        (ACTION_LOGOUT, "Logout"),
        (ACTION_STATUS_CHANGE, "Status Change"),
    )

    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column="user_id")
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    table_name = models.CharField(max_length=255, db_index=True)
    changes = models.JSONField(default=dict)
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Audit_logs"
        indexes = [
            models.Index(fields=["user_id", "-performed_at"], name="audit_user_date_idx"),
            models.Index(fields=["table_name", "action"], name="audit_table_action_idx"),
            models.Index(fields=["-performed_at"], name="audit_performed_at_idx"),
        ]
        ordering = ["-performed_at"]

    def __str__(self):
        return f"{self.user_id} — {self.action} on {self.table_name} at {self.performed_at}"