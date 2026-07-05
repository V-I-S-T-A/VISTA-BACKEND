import uuid
from django.db import models
from document_types.models import DocumentType
from users.models import User
from organizations.models import Organization
from categories.models import Category
from academic_years.models import AcademicYear


class Submission(models.Model):
    STATUS_PENDING = "pending"
    STATUS_UNDER_REVIEW = "under_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_RESUBMISSION_REQUIRED = "resubmission_required"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_UNDER_REVIEW, "Under Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_RESUBMISSION_REQUIRED, "Resubmission Required"),
    )

    submission_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    doc_type_id = models.ForeignKey(DocumentType, on_delete=models.SET_NULL, null=True, db_column="doc_type_id")
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, db_column="submitted_by")
    org_id = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, db_column="org_id")
    category_id = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, db_column="category_id")
    academic_year_id = models.ForeignKey(AcademicYear, on_delete=models.SET_NULL, null=True, db_column="academic_year_id")
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_Submissions"
        indexes = [
            models.Index(fields=["submitted_by", "status"], name="sub_submitter_status_idx"),
            models.Index(fields=["org_id", "status"], name="sub_org_status_idx"),
            models.Index(fields=["status", "-submitted_at"], name="sub_status_date_idx"),
            models.Index(fields=["-submitted_at"], name="sub_submitted_at_idx"),
        ]
        ordering = ["-submitted_at"]

    def __str__(self):
        return self.title