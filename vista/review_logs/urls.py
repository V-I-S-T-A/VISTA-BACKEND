from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ReviewLogViewSet

router = DefaultRouter()
router.register(r"review-logs", ReviewLogViewSet, basename="review-log")

urlpatterns = [
    path("", include(router.urls)),
]