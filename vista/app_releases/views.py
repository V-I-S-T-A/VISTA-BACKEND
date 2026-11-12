from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import AppRelease

class LatestReleaseView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        r = AppRelease.objects.filter(is_active=True).first()
        if not r:
            return Response({"available": False})
        return Response({
            "available": True,
            "version_name": r.version_name,
            "version_code": r.version_code,
            "apk_url": r.apk_url,
            "md5": r.md5,
            "size_bytes": r.size_bytes,
            "notes": r.notes,
            "min_supported_code": r.min_supported_code,
        })