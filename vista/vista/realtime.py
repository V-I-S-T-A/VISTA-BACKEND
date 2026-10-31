"""Short-lived, submission-scoped tickets avoid exposing JWTs in WebSocket URLs."""
from django.core import signing
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from submissions.models import Submission
from submissions.visibility import can_read_submission

SALT = "vista.submission.websocket.v1"

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_ticket(request, submission_id):
    submission = get_object_or_404(Submission, pk=submission_id)
    if not can_read_submission(request.user, submission):
        raise PermissionDenied()
    ticket = signing.dumps({"user_id": str(request.user.pk), "submission_id": str(submission.pk)}, salt=SALT)
    return Response({"ticket": ticket, "expires_in": 45})
