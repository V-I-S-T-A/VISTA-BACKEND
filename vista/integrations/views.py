from datetime import timezone as dt_timezone

from django.shortcuts import redirect
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from users.permissions import IsAdminOrStaff
from .models import GoogleDriveConnection
from .serializers import (
    GoogleDriveConnectionSerializer,
    FolderSelectSerializer,
    FolderCreateSerializer,
)
from . import google_client


class DriveConnectionView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get(self, request):
        connection = getattr(request.user, "drive_connection", None)
        if not connection:
            return Response({"connected": False})
        return Response(
            {"connected": True, **GoogleDriveConnectionSerializer(connection).data}
        )


class DriveAuthStartView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get(self, request):
        scope_mode = request.query_params.get("mode", "existing")
        scopes = (
            google_client.SCOPES_FULL
            if scope_mode == "existing"
            else google_client.SCOPES_CREATE_ONLY
        )
        flow = google_client.build_flow(scopes, state=str(request.user.user_id))
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return Response({"authorization_url": auth_url})


class DriveAuthCallbackView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get(self, request):
        code = request.query_params.get("code")
        state = request.query_params.get("state")

        if str(request.user.user_id) != state:
            return Response({"detail": "State mismatch."}, status=status.HTTP_400_BAD_REQUEST)

        scope_param = request.query_params.get("scope", "")
        scopes = scope_param.split(" ") if scope_param else google_client.SCOPES_CREATE_ONLY

        flow = google_client.build_flow(scopes, state=state)
        flow.fetch_token(code=code)
        creds = flow.credentials

        connection, _ = GoogleDriveConnection.objects.update_or_create(
            staff=request.user,
            defaults={
                "google_account_email": request.query_params.get("email", ""),
                "token_expiry": creds.expiry.replace(tzinfo=dt_timezone.utc),
                "scopes": scopes,
                "is_active": True,
            },
        )
        connection.access_token = creds.token
        connection.refresh_token = creds.refresh_token
        connection.save()

        return Response(
            {"detail": "Google account connected. Now choose or create a folder."},
            status=status.HTTP_200_OK,
        )


class DriveFolderListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get(self, request):
        connection = getattr(request.user, "drive_connection", None)
        if not connection:
            return Response({"detail": "Connect Google Drive first."}, status=status.HTTP_400_BAD_REQUEST)
        query = request.query_params.get("search")
        folders = google_client.list_folders(connection, query=query)
        return Response({"folders": folders})


class DriveFolderSelectView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def post(self, request):
        connection = getattr(request.user, "drive_connection", None)
        if not connection:
            return Response({"detail": "Connect Google Drive first."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FolderSelectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        connection.folder_mode = GoogleDriveConnection.FOLDER_MODE_EXISTING
        connection.folder_id = serializer.validated_data["folder_id"]
        connection.folder_name = serializer.validated_data["folder_name"]
        connection.save(update_fields=["folder_mode", "folder_id", "folder_name", "updated_at"])

        return Response(GoogleDriveConnectionSerializer(connection).data)


class DriveFolderCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def post(self, request):
        connection = getattr(request.user, "drive_connection", None)
        if not connection:
            return Response({"detail": "Connect Google Drive first."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FolderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        folder = google_client.create_folder(connection, serializer.validated_data["folder_name"])

        connection.folder_mode = GoogleDriveConnection.FOLDER_MODE_CREATED
        connection.folder_id = folder["id"]
        connection.folder_name = folder["name"]
        connection.save(update_fields=["folder_mode", "folder_id", "folder_name", "updated_at"])

        return Response(GoogleDriveConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)


class DriveDisconnectView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def post(self, request):
        connection = getattr(request.user, "drive_connection", None)
        if connection:
            connection.is_active = False
            connection.save(update_fields=["is_active", "updated_at"])
        return Response({"detail": "Google Drive disconnected."})