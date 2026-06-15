import uuid
from django.db import models

class AcademicYear(models.Model):
    academic_year_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    year = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_Acacdemic_Year"