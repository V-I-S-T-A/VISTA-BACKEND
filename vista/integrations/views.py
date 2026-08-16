from datetime import timezone as dt_timezone

from django.shortcuts import redirect
from django.http import HttpResponse
from django.conf import settings
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser

from users.permissions import IsAdminOrStaff
from .models import GoogleDriveConnection
from .serializers import (
    GoogleDriveConnectionSerializer,
    FolderSelectSerializer,
    FolderCreateSerializer,
)
from . import google_client
import os
from django.utils import timezone
from .serializers import DriveUploadSerializer
from urllib.parse import urlencode
from django.core import signing
from django.shortcuts import redirect
from rest_framework.permissions import AllowAny
from users.models import User

APP_CALLBACK_URL = "vista-app://drive-callback"
WEB_CALLBACK_URL = "http://localhost:5173/staff/gdrive-sync/callback"
DRIVE_STATE_SALT = "vista-drive-oauth-state"

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
        client_type = request.query_params.get("client_type", "web")  # "web" or "mobile"
        
        scopes = (
            google_client.SCOPES_FULL
            if scope_mode == "existing"
            else google_client.SCOPES_CREATE_ONLY
        )
        
        state_data = {
            "user_id": str(request.user.user_id),
            "client_type": client_type
        }
        state = signing.dumps(state_data, salt=DRIVE_STATE_SALT)
        flow = google_client.build_flow(scopes, state=state)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return Response({"authorization_url": auth_url})


class DriveAuthCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get("code")
        state = request.query_params.get("state")

        if not code or not state:
            return self._redirect_with_error("Missing authorization code.", state)

        try:
            state_data = signing.loads(state, salt=DRIVE_STATE_SALT, max_age=600)
            user_id = state_data.get("user_id") if isinstance(state_data, dict) else state_data
            client_type = state_data.get("client_type", "web") if isinstance(state_data, dict) else "web"
        except signing.BadSignature:
            return self._redirect_with_error("Sign-in link expired. Please try again.", state)

        try:
            user = User.objects.get(user_id=user_id, is_active=True)
        except User.DoesNotExist:
            return self._redirect_with_error("User not found.", state)

        scope_param = request.query_params.get("scope", "")
        scopes = scope_param.split(" ") if scope_param else google_client.SCOPES_CREATE_ONLY

        flow = google_client.build_flow(scopes, state=state)
        try:
            flow.fetch_token(code=code)
        except Exception:
            return self._redirect_with_error("Could not complete Google sign-in.", state)
        creds = flow.credentials

        # Extract email from ID token (if available)
        google_account_email = ""
        if hasattr(creds, 'id_token') and creds.id_token:
            import json
            try:
                # ID token is a JWT, decode the payload
                import base64
                parts = creds.id_token.split('.')
                if len(parts) >= 2:
                    payload = parts[1]
                    # Add padding if needed
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += '=' * padding
                    decoded = base64.urlsafe_b64decode(payload)
                    token_data = json.loads(decoded)
                    google_account_email = token_data.get('email', '')
            except Exception:
                pass

        connection, _ = GoogleDriveConnection.objects.update_or_create(
            staff=user,
            defaults={
                "google_account_email": google_account_email,
                "token_expiry": creds.expiry.replace(tzinfo=dt_timezone.utc),
                "scopes": scopes,
                "is_active": True,
            },
        )
        connection.access_token = creds.token
        connection.refresh_token = creds.refresh_token
        connection.save()

        return self._redirect_success(client_type)

    def _redirect_with_error(self, detail, state=None):
        """Redirect to appropriate client with error message."""
        # Try to extract client_type from state
        client_type = "web"
        if state:
            try:
                state_data = signing.loads(state, salt=DRIVE_STATE_SALT, max_age=600)
                client_type = state_data.get("client_type", "web") if isinstance(state_data, dict) else "web"
            except:
                pass
        
        params = {"status": "error", "detail": detail}
        query_string = urlencode(params)
        
        if client_type == "mobile":
            # Use HTML meta refresh for custom protocol redirects
            url = f"{APP_CALLBACK_URL}?{query_string}"
            html = f"""
            <html>
                <head>
                    <meta http-equiv="refresh" content="0; url={url}">
                </head>
                <body>
                    <p>Redirecting...</p>
                    <p>If you are not redirected, <a href="{url}">click here</a>.</p>
                </body>
            </html>
            """
            return HttpResponse(html)
        else:
            url = f"{WEB_CALLBACK_URL}?{query_string}"
            return redirect(url)

    def _redirect_success(self, client_type):
        """Redirect to appropriate client with success message."""
        params = {"status": "success"}
        query_string = urlencode(params)
        
        if client_type == "mobile":
            # Use HTML meta refresh for custom protocol redirects
            url = f"{APP_CALLBACK_URL}?{query_string}"
            html = f"""
            <html>
                <head>
                    <meta http-equiv="refresh" content="0; url={url}">
                </head>
                <body>
                    <p>Redirecting...</p>
                    <p>If you are not redirected, <a href="{url}">click here</a>.</p>
                </body>
            </html>
            """
            return HttpResponse(html)
        else:
            url = f"{WEB_CALLBACK_URL}?{query_string}"
            return redirect(url)


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

class DriveFolderPathPreviewView(APIView):
    """GET /api/drive/folder-path-preview/?submission_id=... — lets the
    mobile UI show the auto-folder path before anything is created."""
    permission_classes = [IsAuthenticated, IsAdminOrStaff]

    def get(self, request):
        from submissions.models import Submission

        submission_id = request.query_params.get("submission_id")
        if not submission_id:
            return Response({"detail": "submission_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            submission = Submission.objects.select_related("academic_year_id", "org_id", "doc_type_id").get(
                submission_id=submission_id
            )
        except Submission.DoesNotExist:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)

        segments = []
        if submission.academic_year_id:
            segments.append(submission.academic_year_id.year)
        if submission.org_id:
            segments.append(submission.org_id.name)
        segments.append(submission.doc_type_id.name if submission.doc_type_id else "Uncategorized")

        return Response({"path_segments": segments, "suggested_file_name": submission.title})


class DriveSubmissionUploadView(APIView):
    """POST /api/drive/upload/ — the manual archiving action from the
    Review Panel. Only allowed once a submission is approved."""
    permission_classes = [IsAuthenticated, IsAdminOrStaff]
    parser_classes = [MultiPartParser]

    def post(self, request):
        from submissions.models import Submission
        from documents.models import Document
        from documents.serializers import DocumentSerializer

        serializer = DriveUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        connection = getattr(request.user, "drive_connection", None)
        if not connection or not connection.is_active:
            return Response({"detail": "Connect Google Drive first."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            submission = Submission.objects.select_related("academic_year_id", "org_id", "doc_type_id").get(
                submission_id=data["submission_id"]
            )
        except Submission.DoesNotExist:
            return Response({"detail": "Submission not found."}, status=status.HTTP_404_NOT_FOUND)

        if submission.status != Submission.STATUS_APPROVED:
            return Response(
                {"detail": "Only approved submissions can be archived to Drive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        use_auto_folder = data.get("use_auto_folder", True)
        manual_folder_id = data.get("folder_id")
        path_segments = None

        if use_auto_folder or not manual_folder_id:
            folder, path_segments = google_client.resolve_submission_folder_path(connection, submission)
            target_folder_id = folder["id"]
        else:
            target_folder_id = manual_folder_id

        uploaded_file = data["file"]
        file_name = data.get("file_name") or submission.title
        _, ext = os.path.splitext(uploaded_file.name)
        if ext and not file_name.lower().endswith(ext.lower()):
            file_name = f"{file_name}{ext}"

        file_bytes = uploaded_file.read()
        mime_type = uploaded_file.content_type or "application/octet-stream"

        try:
            uploaded = google_client.upload_file_to_folder(
                connection=connection,
                folder_id=target_folder_id,
                file_name=file_name,
                file_bytes=file_bytes,
                mime_type=mime_type,
            )
        except Exception:
            return Response(
                {"detail": "Failed to upload the file to Google Drive. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Link the archived file to the submission (auto-versioned, same
        # pattern as DocumentCreateSerializer.create()).
        Document.objects.filter(submission_id=submission, is_current=True).update(is_current=False)
        latest = Document.objects.filter(submission_id=submission).order_by("-version").first()
        next_version = (latest.version + 1) if latest else 1

        document = Document.objects.create(
            submission_id=submission,
            file_name=file_name,
            file_url=uploaded.get("webViewLink", ""),
            mime_type=mime_type,
            file_size_kb=max(1, len(file_bytes) // 1024),
            version=next_version,
            is_current=True,
        )

        connection.last_synced_at = timezone.now()
        connection.save(update_fields=["last_synced_at"])

        return Response(
            {
                "detail": "Document archived to Google Drive.",
                "drive_file_id": uploaded.get("id"),
                "drive_view_link": uploaded.get("webViewLink"),
                "folder_path": path_segments,
                "document": DocumentSerializer(document).data,
            },
            status=status.HTTP_201_CREATED,
        )