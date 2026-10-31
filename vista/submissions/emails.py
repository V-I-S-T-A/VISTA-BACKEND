"""
Status-change email notifications for Submissions.

Sent from `SubmissionStatusUpdateSerializer.update()` (submissions/serializers.py)
whenever a submission's status actually changes. The email goes to
`submission.submitted_by.email` only -- never to staff or admin.

Reviewer remarks are included only when the new status is
`resubmission_required`. In the review panel, "Return for Revision" maps to
this same backend value, so one rule covers both.
"""

import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import escape

logger = logging.getLogger(__name__)

# The OSA operates in the Philippines; show dates as the recipient sees them
# rather than in the server's UTC.
LOCAL_TZ = ZoneInfo("Asia/Manila")

STATUS_LABELS = {
    "pending": "Pending",
    "under_review": "On Process",
    "approved": "Approved",
    "rejected": "Rejected",
    "resubmission_required": "Resubmission Required",
}

# Remarks are shown to the student only for these statuses.
STATUSES_WITH_REMARKS = {"resubmission_required"}

STATUS_MESSAGES = {
    "pending": (
        "Your submission has been placed back in the queue and is waiting "
        "to be reviewed."
    ),
    "under_review": (
        "Our office has started reviewing your submission. You will receive "
        "another email once a decision has been made."
    ),
    "approved": (
        "We are pleased to inform you that your submission has been "
        "approved. No further action is needed on your part."
    ),
    "rejected": (
        "After review, your submission was not approved. If you have "
        "questions about this decision, please get in touch with the "
        "Office of Student Affairs."
    ),
    "resubmission_required": (
        "Your submission needs a few changes before we can proceed. Please "
        "read the remarks below, update your document, and submit it again."
    ),
}


def _label(status):
    return STATUS_LABELS.get(status, (status or "").replace("_", " ").title())


def _today():
    now = timezone.now().astimezone(LOCAL_TZ)
    return f"{now:%B} {now.day}, {now.year}"


def _build_text_body(submission, name, new_status, remarks, date_str):
    submission_url = _submission_url(submission)
    lines = [
        f"Dear {name},",
        "",
        f'The status of your submission, "{submission.title}", has been '
        f"updated to {_label(new_status)}.",
        "",
        STATUS_MESSAGES.get(new_status, ""),
    ]

    if remarks:
        lines += ["", "Remarks from the reviewer:", remarks]

    lines += [
        "",
        f"Document: {submission.title}",
        f"Status: {_label(new_status)}",
        f"Date: {date_str}",
        "",
        "You may log in to VISTA at any time to view your submission.",
        f"View this submission: {submission_url}",
        "",
        "Regards,",
        "Office of Student Affairs",
        "",
        "---",
        "This is an automated message. Please do not reply to this email.",
    ]
    return "\n".join(lines)


def _build_html_body(submission, name, new_status, remarks, date_str):
    # Django's escape() already escapes quotes; it does not accept a `quote` kwarg.
    submission_url = escape(_submission_url(submission))
    title = escape(submission.title)
    label = escape(_label(new_status))
    message = escape(STATUS_MESSAGES.get(new_status, ""))

    font = "font-family: Arial, Helvetica, sans-serif;"

    remarks_block = ""
    if remarks:
        remarks_block = f"""
              <p style="margin: 0 0 6px 0; {font} font-size: 13px; color: #555555;">
                Remarks from the reviewer:
              </p>
              <div style="margin: 0 0 24px 0; padding: 4px 0 4px 16px; border-left: 3px solid #1f5cae; {font} font-size: 15px; line-height: 1.6; color: #222222; white-space: pre-wrap;">{escape(remarks)}</div>"""

    return f"""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Submission update</title>
  </head>
  <body style="margin: 0; padding: 0; background-color: #f4f5f7;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f5f7;">
      <tr>
        <td align="center" style="padding: 24px 12px;">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width: 100%; max-width: 560px; background-color: #ffffff; border-top: 4px solid #1f5cae;">
            <tr>
              <td style="padding: 28px 32px 8px 32px; {font} font-size: 13px; letter-spacing: 0.5px; color: #1f5cae;">
                <strong>V.I.S.T.A.</strong> &nbsp;|&nbsp; Office of Student Affairs
              </td>
            </tr>
            <tr>
              <td style="padding: 20px 32px 8px 32px; {font} font-size: 15px; line-height: 1.6; color: #222222;">
                <p style="margin: 0 0 16px 0;">Dear {escape(name)},</p>
                <p style="margin: 0 0 16px 0;">
                  The status of your submission, <strong>&ldquo;{title}&rdquo;</strong>,
                  has been updated to <strong>{label}</strong>.
                </p>
                <p style="margin: 0 0 24px 0;">{message}</p>{remarks_block}
                <table role="presentation" cellpadding="0" cellspacing="0" style="margin: 0 0 24px 0; {font} font-size: 14px; color: #222222;">
                  <tr>
                    <td style="padding: 3px 20px 3px 0; color: #777777;">Document</td>
                    <td style="padding: 3px 0;">{title}</td>
                  </tr>
                  <tr>
                    <td style="padding: 3px 20px 3px 0; color: #777777;">Status</td>
                    <td style="padding: 3px 0;">{label}</td>
                  </tr>
                  <tr>
                    <td style="padding: 3px 20px 3px 0; color: #777777;">Date</td>
                    <td style="padding: 3px 0;">{date_str}</td>
                  </tr>
                </table>
                <p style="margin: 0 0 24px 0;">
                  You may log in to VISTA at any time to view your submission.
                </p>
                <p style="margin: 0 0 24px 0;"><a href="{submission_url}" style="color: #1f5cae; font-weight: 700;">View this submission</a></p>
                <p style="margin: 0 0 8px 0;">
                  Regards,<br />
                  Office of Student Affairs
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding: 16px 32px 24px 32px; border-top: 1px solid #e5e5e5; {font} font-size: 12px; line-height: 1.5; color: #888888;">
                This is an automated message. Please do not reply to this email.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def send_status_change_email(submission, old_status, new_status, remarks_text=""):
    """
    Emails the submission's owner about a status change.

    `old_status` is accepted for the caller's convenience but is not shown in
    the email. Remarks are included only for `resubmission_required`.
    Failures are raised to the caller, which logs and swallows them so a mail
    problem never affects the review decision.
    """
    submitted_by = getattr(submission, "submitted_by", None)
    recipient = getattr(submitted_by, "email", None)
    if not recipient:
        logger.warning(
            "Skipping status-change email for submission %s: no submitted_by email on file.",
            submission.submission_id,
        )
        return

    name = submitted_by.get_full_name() or recipient
    remarks = (remarks_text or "").strip() if new_status in STATUSES_WITH_REMARKS else ""
    date_str = _today()

    message = EmailMultiAlternatives(
        subject=f'VISTA: "{submission.title}" is now {_label(new_status)}',
        body=_build_text_body(submission, name, new_status, remarks, date_str),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    message.attach_alternative(
        _build_html_body(submission, name, new_status, remarks, date_str),
        "text/html",
    )
    sent = message.send(fail_silently=False)
    if sent != 1:
        logger.warning(
            "Status-change email was not accepted by the configured email backend for submission %s.",
            submission.submission_id,
        )
    return sent


def send_submission_received_email(submission):
    """Receipt for a newly saved entry, addressed only to its submitter."""
    submitter = submission.submitted_by
    if not submitter or not submitter.email:
        return 0
    name = submitter.get_full_name() or submitter.email
    url = _submission_url(submission)
    message = EmailMultiAlternatives(
        subject=f'VISTA: "{submission.title}" has been received',
        body=(f'Dear {name},\n\nYour submission, "{submission.title}", has been received '
              f'and is now On Process.\n\nView this submission: {url}\n\n'
              'Office of Student Affairs\nThis is an automated message. Please do not reply.'),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[submitter.email],
    )
    message.attach_alternative(
        f'<html><body><p>Dear {escape(name)},</p><p>Your submission, '
        f'<strong>{escape(submission.title)}</strong>, has been received and is now On Process.</p>'
        f'<p><a href="{escape(url)}">View this submission</a></p>'
        '<p>Office of Student Affairs</p><small>This is an automated message. Please do not reply.</small></body></html>',
        'text/html',
    )
    return message.send(fail_silently=False)


def send_priority_change_email(submission):
    """Email the submitter when staff newly marks a submission as priority."""
    submitted_by = getattr(submission, "submitted_by", None)
    recipient = getattr(submitted_by, "email", None)
    if not recipient:
        logger.warning(
            "Skipping priority email for submission %s: no submitted_by email on file.",
            submission.submission_id,
        )
        return 0

    name = submitted_by.get_full_name() or recipient
    submission_url = _submission_url(submission)
    safe_title = escape(submission.title)
    safe_url = escape(submission_url)
    message = EmailMultiAlternatives(
        subject=f'VISTA: "{submission.title}" has been marked as a priority',
        body=(
            f"Dear {name},\n\n"
            f'Your submission, "{submission.title}", has been marked as a priority by VISTA staff.\n\n'
            f"View this submission: {submission_url}\n\n"
            "Office of Student Affairs\n"
            "This is an automated message. Please do not reply."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    message.attach_alternative(
        f'<!doctype html><html><body><p>Dear {escape(name)},</p>'
        f'<p>Your submission, <strong>&ldquo;{safe_title}&rdquo;</strong>, has been marked as a priority by VISTA staff.</p>'
        f'<p><a href="{safe_url}">View this submission</a></p>'
        "<p>Office of Student Affairs</p>"
        "<small>This is an automated message. Please do not reply.</small></body></html>",
        "text/html",
    )
    sent = message.send(fail_silently=False)
    if sent != 1:
        logger.warning(
            "Priority email was not accepted by the configured email backend for submission %s.",
            submission.submission_id,
        )
    return sent


def _submission_url(submission):
    base = getattr(settings, "FRONTEND_URL", "").rstrip("/")
    return f"{base}/student/review-tracker/{submission.submission_id}"
