"""Student read scope shared by submission lists and their update history."""
from django.db.models import Q


def student_submission_scope(user, prefix=""):
    # Keep existing owner access, including legacy entries without an organization.
    scope = Q(**{f"{prefix}submitted_by": user})
    if user.org_id_id and user.org_joined_at:
        scope |= Q(**{
            f"{prefix}org_id": user.org_id_id,
            f"{prefix}submitted_at__gte": user.org_joined_at,
        })
    # A missing organization must never group unrelated, unassigned students.
    return scope


def can_read_submission(user, submission):
    return user.role in ("admin", "staff") or (
        user.role == "student" and (
            submission.submitted_by_id == user.pk
            or bool(user.org_id_id and user.org_joined_at
                    and submission.org_id_id == user.org_id_id
                    and submission.submitted_at >= user.org_joined_at)
        )
    )


def can_reply_to_submission(user, submission):
    return user.role in ("admin", "staff") or (
        user.role == "student" and submission.submitted_by_id == user.pk
    )
