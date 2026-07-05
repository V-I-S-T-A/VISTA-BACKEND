import uuid
from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
from users.models import User


def _fernet():
    return Fernet(settings.DRIVE_TOKEN_ENCRYPTION_KEY.encode())


class GoogleDriveConnection(models.Model):
    FOLDER_MODE_EXISTING = "existing"
    FOLDER_MODE_CREATED = "created"

    FOLDER_MODE_CHOICES = (
        (FOLDER_MODE_EXISTING, "Picked Existing Folder"),
        (FOLDER_MODE_CREATED, "App-Created Folder"),
    )

    connection_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.OneToOneField(User, on_delete=models.CASCADE, related_name="drive_connection")

    google_account_email = models.EmailField()
    _access_token = models.TextField(db_column="access_token")
    _refresh_token = models.TextField(db_column="refresh_token")
    token_expiry = models.DateTimeField()
    scopes = models.JSONField(default=list)

    folder_mode = models.CharField(max_length=20, choices=FOLDER_MODE_CHOICES)
    folder_id = models.CharField(max_length=255, blank=True)
    folder_name = models.CharField(max_length=255, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_Google_Drive_Connections"
        indexes = [
            models.Index(fields=["staff", "is_active"], name="gdrive_staff_active_idx"),
        ]

    def __str__(self):
        return f"{self.staff.email} -> {self.folder_name or self.folder_id}"

    @property
    def access_token(self):
        return _fernet().decrypt(self._access_token.encode()).decode()

    @access_token.setter
    def access_token(self, value):
        self._access_token = _fernet().encrypt(value.encode()).decode()

    @property
    def refresh_token(self):
        return _fernet().decrypt(self._refresh_token.encode()).decode()

    @refresh_token.setter
    def refresh_token(self, value):
        self._refresh_token = _fernet().encrypt(value.encode()).decode()