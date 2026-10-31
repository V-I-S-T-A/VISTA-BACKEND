"""Single-port HTTP/ASGI and mobile-compatible, origin-protected WebSockets."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vista.settings")
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

from django.conf import settings
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import OriginValidator
from notifications.routing import websocket_urlpatterns


class NativeCompatibleOriginValidator:
    """Check browser Origin headers, allow origin-less native clients with JWT auth.

    Browser WebSocket APIs automatically send Origin and cannot strip it;
    native mobile clients may legitimately omit Origin.
    """
    def __init__(self, app, allowed_origins):
        self.app = app
        self.browser_validator = OriginValidator(app, allowed_origins)

    async def __call__(self, scope, receive, send):
        headers = scope.get("headers", [])
        if any(name.lower() == b"origin" for name, _ in headers):
            return await self.browser_validator(scope, receive, send)
        return await self.app(scope, receive, send)


websocket_app = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
allowed_origins = settings.CORS_ALLOWED_ORIGINS + [
    f"{scheme}://{host}" for host in settings.ALLOWED_HOSTS
    if host not in ("*", "") for scheme in ("http", "https")
]

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": NativeCompatibleOriginValidator(websocket_app, allowed_origins),
})
