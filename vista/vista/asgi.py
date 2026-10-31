"""ASGI app for HTTP and authenticated submission WebSocket events."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vista.settings")
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()
from channels.routing import ProtocolTypeRouter, URLRouter
from vista.realtime_routing import websocket_urlpatterns
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(websocket_urlpatterns),
})
