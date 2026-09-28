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
    "under_review": "Under Review",
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
        "",
        "Regards,",
        "Office of Student Affairs",
        "",
        "---",
        "This is an automated message. Please do not reply to this email.",
    ]
    return "\n".join(lines)


def _build_html_body(submission, name, new_status, remarks, date_str):
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
    message.send(fail_silently=False)