"""ASGI entrypoint: HTTP and shared notifications socket."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vista.settings")
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import OriginValidator
from django.conf import settings
from notifications.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": OriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
        settings.CORS_ALLOWED_ORIGINS + [
            f"{scheme}://{host}" for host in settings.ALLOWED_HOSTS
            if host not in ("*", "") for scheme in ("https", "http")
        ]
    ),
})
