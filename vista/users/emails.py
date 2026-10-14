import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

def send_welcome_email(user, temp_password):
    send_mail(
        subject="VISTA — Your account has been created",
        message=(
            f"Hi {user.first_name},\n\n"
            "An account has been created for you on VISTA.\n\n"
            f"Email: {user.email}\n"
            f"Temporary password: {temp_password}\n\n"
            "Please log in and change your password right away.\n\n"
            "— VISTA, Office of Student Affairs"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )