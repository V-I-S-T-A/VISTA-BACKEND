import uuid
import random
from django.db import models, transaction
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from organizations.models import Organization
from datetime import timedelta
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, first_name, last_name, password=None, role="student", membership_actor=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            **extra_fields,
        )
        user.set_password(password)
        user._membership_actor = membership_actor
        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name, last_name, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, first_name, last_name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ("student", "Student"),
        ("staff", "Staff"),
        ("admin", "Admin"),
    )

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org_id = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, db_column="org_id")
    # Unknown legacy dates deliberately remain NULL. Ordinary clients cannot set it.
    org_joined_at = models.DateTimeField(null=True, blank=True, editable=False)
    first_name = models.CharField(max_length=150, db_index=True)
    last_name = models.CharField(max_length=150, db_index=True)
    email = models.CharField(max_length=255, unique=True)
    phone_number = models.CharField(max_length=13, blank=True, default="")
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=100, blank=True, default="")
    role = models.CharField(max_length=100, choices=ROLE_CHOICES, default="student", db_index=True)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    must_change_password = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]
    

    class Meta:
        db_table = "tbl_Users"
        indexes = [
            models.Index(fields=["role", "is_active"], name="user_role_active_idx"),
            models.Index(fields=["-created_at"], name="user_created_at_idx"),
            models.Index(fields=["last_name", "first_name"], name="user_name_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        using = kwargs.get("using") or self._state.db or "default"
        fields = kwargs.get("update_fields")
        if fields is not None and not fields:
            return
        with transaction.atomic(using=using):
            previous = None
            if not self._state.adding:
                previous = type(self).objects.using(using).select_for_update().get(pk=self.pk)
            assignment_written = fields is None or "org_id" in fields or "org_id_id" in fields
            changed = assignment_written and (
                (previous is None and self.org_id_id is not None)
                or (previous is not None and previous.org_id_id != self.org_id_id)
            )
            if changed:
                self.org_joined_at = timezone.now() if self.org_id_id else None
                if fields is not None:
                    kwargs["update_fields"] = set(fields) | {"org_joined_at"}
            else:
                # Profile saves and stale instances must not reset/backdate membership.
                self.org_joined_at = previous.org_joined_at if previous else None
            super().save(*args, **kwargs)
            if changed:
                OrganizationMembershipAudit.objects.using(using).create(
                    user=self, actor=getattr(self, "_membership_actor", None),
                    previous_org_id=previous.org_id_id if previous else None,
                    org_id_value=self.org_id_id,
                    previous_joined_at=previous.org_joined_at if previous else None,
                    joined_at=self.org_joined_at, reason="assignment",
                )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.first_name

class OrganizationMembershipAudit(models.Model):
    """Append-only evidence of assignments and administrator date verification."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="membership_audits")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="membership_actions")
    previous_org_id = models.UUIDField(null=True)
    org_id_value = models.UUIDField(null=True)
    previous_joined_at = models.DateTimeField(null=True)
    joined_at = models.DateTimeField(null=True)
    reason = models.CharField(max_length=20, choices=(("assignment", "Assignment"), ("verification", "Verification")))
    evidence = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "-pk"]


class PasswordChangeCode(models.Model):
    code_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_change_codes")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "tbl_Password_Change_Codes"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="pwcode_user_created_idx"),
        ]

    @classmethod
    def generate_for(cls, user):
        code = f"{random.randint(0, 999999):06d}"
        return cls.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at
