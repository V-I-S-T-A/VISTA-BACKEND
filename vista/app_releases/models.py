from django.db import models

class AppRelease(models.Model):
    version_name = models.CharField(max_length=20)            # "1.0.5" (display only)
    version_code = models.PositiveIntegerField(unique=True)   # must match the APK's versionCode
    apk_url = models.URLField(max_length=500)                 # direct HTTPS link
    md5 = models.CharField(max_length=32)                     # md5 of the APK file
    size_bytes = models.BigIntegerField(default=0)
    notes = models.TextField(blank=True)
    min_supported_code = models.PositiveIntegerField(default=0)  # below this = forced update
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_App_Releases"
        ordering = ["-version_code"]