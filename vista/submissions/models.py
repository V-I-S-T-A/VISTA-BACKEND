import uuid
from django.db import models
from document_types.models import DocumentType
from users.models import User
from organizations.models import Organization
from categories.models import Category
from academic_years.models import AcademicYear

class Submission(models.Model):
    submission_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc_type_id = models.ForeignKey(DocumentType, on_delete=models.SET_NULL, null=True, db_column="doc_type_id")
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column="submitted_by")
    org_id = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, db_column="org_id")
    category_id = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, db_column="category_id")
    academic_year_id = models.ForeignKey(AcademicYear, on_delete=models.SET_NULL, null=True, db_column="academic_year_id")
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=100)
    submitted_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_Submissions"