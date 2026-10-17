"""Formal transactional emails with HTML and plain-text alternatives."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _send(user, subject, context):
    context = {"name": user.first_name, "website_url": settings.FRONTEND_URL.rstrip("/") + "/", **context}
    email = EmailMultiAlternatives(subject, render_to_string("emails/transactional.txt", context), settings.DEFAULT_FROM_EMAIL, [user.email])
    email.attach_alternative(render_to_string("emails/transactional.html", context), "text/html")
    return email.send(fail_silently=False)


def send_welcome_email(user, temp_password):
    return _send(user, "VISTA | Your account is ready", {
        "title": "Welcome to VISTA",
        "intro": "Your VISTA account has been created by an administrator. Use the credentials below to sign in.",
        "account_email": user.email, "temporary_password": temp_password,
        "notice": "Change your temporary password immediately after signing in. Do not share your credentials.",
        "button_label": "Sign in to VISTA",
    })


def send_password_code_email(user, record, *, reset=False):
    action = "password reset" if reset else "password change"
    return _send(user, f"VISTA | Your {action} verification code", {
        "title": "Password reset verification" if reset else "Password change verification",
        "intro": f"We received a request for a {action} on your VISTA account. Enter this one-time code in VISTA to continue.",
        "code": record.code,
        "notice": "This code expires in 10 minutes. Never share it. If you did not request this, ignore this email; your password has not been changed by this request.",
        "button_label": "Open VISTA",
    })
