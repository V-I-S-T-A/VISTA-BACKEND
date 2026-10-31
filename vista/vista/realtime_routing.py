from django.urls import re_path
from .realtime_consumers import SubmissionEventsConsumer

websocket_urlpatterns = [
    re_path(r"^ws/submissions/(?P<submission_id>[0-9a-fA-F-]+)/$", SubmissionEventsConsumer.as_asgi()),
]
