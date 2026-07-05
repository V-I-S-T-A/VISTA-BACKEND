from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import DocumentTypeViewSet

router = DefaultRouter()
router.register(r"document-types", DocumentTypeViewSet, basename="document-type")

urlpatterns = [
    path("", include(router.urls)),
]