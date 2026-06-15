import uuid
from django.db import models
from users.models import User

class AuditLog(models.Model):
    audit_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column="user_id")
    action = models.CharField(max_length=255)
    table_name = models.CharField(max_length=255)
    changes = models.JSONField()
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Audit_logs"