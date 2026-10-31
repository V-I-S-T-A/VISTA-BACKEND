"""Opt-in isolated regression settings; never used by ordinary application access.

Run: python manage.py test <modules> --settings=vista.test_settings
No shared database, Redis queue, mailbox, or push delivery is used.
"""
from .settings import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
NOTIFICATIONS_PUSH_ENABLED = False
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CACHES = {name: {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": name}
          for name in ("default", "push_delivery")}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
