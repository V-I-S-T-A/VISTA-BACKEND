import io
from datetime import datetime, timezone

from django.conf import settings
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import logging

SCOPES_CREATE_ONLY = ["https://www.googleapis.com/auth/drive.file"]
SCOPES_FULL = ["https://www.googleapis.com/auth/drive"]
APPROVED_FOLDER_NAME = "Approved"

logger = logging.getLogger(__name__)

class DriveAuthExpired(Exception):
    """
    Raised whenever the stored Drive OAuth credentials can no longer be
    used -- refresh token revoked, expired from inactivity (a Google Cloud
    OAuth consent screen still in "Testing" publishing status caps refresh
    tokens at 7 days), or the API itself rejects a request as unauthorized.

    There is no retry that fixes this -- the staff member has to go
    through "Sign in with Google" again. Callers catch this, flip the
    connection's `is_active` to False, and surface a reconnect prompt
    instead of a generic failure message.
    """


def build_flow(scopes, state=None):
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
            }
        },
        scopes=scopes,
        state=state,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    return flow


def credentials_from_connection(connection):
    creds = Credentials(
        token=connection.access_token,
        refresh_token=connection.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=connection.scopes,
    )

    if creds.expired or not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise DriveAuthExpired(
                "Google Drive credentials could not be refreshed; the "
                "connection must be re-authorized."
            ) from exc
        connection.access_token = creds.token
        connection.token_expiry = creds.expiry.replace(tzinfo=timezone.utc)
        connection.save(update_fields=["_access_token", "token_expiry", "updated_at"])

    return creds


def _execute(request):
    """
    Runs a googleapiclient request and normalizes auth-shaped HTTP errors
    (401/403) into DriveAuthExpired -- a revoked grant can surface either
    as a failed token refresh OR as a 401/403 on the very next API call if
    the access token hadn't technically expired yet. Every `.execute()`
    call in this module goes through here instead of calling it directly.
    """
    try:
        return request.execute()
    except HttpError as exc:
        status_code = getattr(exc.resp, "status", None)
        if status_code in (401, 403):
            raise DriveAuthExpired(
                "Google Drive rejected the request as unauthorized; the "
                "connection must be re-authorized."
            ) from exc
        raise


def get_drive_service(connection):
    creds = credentials_from_connection(connection)
    return build("drive", "v3", credentials=creds)


def list_folders(connection, query=None):
    service = get_drive_service(connection)
    q = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if query:
        q += f" and name contains '{query}'"
    results = _execute(service.files().list(q=q, fields="files(id, name)", pageSize=50))
    return results.get("files", [])


def create_folder(connection, name):
    service = get_drive_service(connection)
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    return _execute(service.files().create(body=metadata, fields="id, name"))


def find_or_create_folder(connection, name, parent_id=None, service=None):
    """
    Looks for a folder named `name` under `parent_id` (or Drive root).
    Creates it if it doesn't exist. Returns the folder dict {id, name}.
    Pass `service` to reuse an existing Drive client.
    """
    service = service or get_drive_service(connection)
    safe_name = name.replace("'", "\\'")
    q = (
        "mimeType = 'application/vnd.google-apps.folder' and trashed = false "
        f"and name = '{safe_name}'"
    )
    q += f" and '{parent_id}' in parents" if parent_id else " and 'root' in parents"

    files = _execute(service.files().list(q=q, fields="files(id, name)", pageSize=1)).get("files", [])
    if files:
        return files[0]

    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    return _execute(service.files().create(body=metadata, fields="id, name"))


def ensure_folder_path(connection, base_folder_id, path_segments):
    """
    Ensures a nested folder path exists under base_folder_id, creating any
    missing segments along the way. Returns the id of the deepest folder.
    """
    current_parent_id = base_folder_id
    for segment in path_segments:
        clean_segment = (segment or "").strip()
        if not clean_segment:
            continue
        current_parent_id = find_or_create_folder(
            connection, clean_segment, parent_id=current_parent_id
        )["id"]
    return current_parent_id


def _upload(service, folder_id, file_name, file_bytes, mime_type):
    metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
    return _execute(service.files().create(body=metadata, media_body=media, fields="id, webViewLink"))


def upload_file_to_folder(connection, folder_id, file_name, file_bytes, mime_type):
    return _upload(get_drive_service(connection), folder_id, file_name, file_bytes, mime_type)


def upload_files_to_folder(connection, folder_id, files):
    """
    Uploads several (file_name, file_bytes, mime_type) tuples into one folder.

    The Drive service (credential refresh + API discovery) is built once and
    reused. One failing file doesn't stop the rest; auth errors are re-raised
    because they would fail every remaining file too.

    Returns (uploaded_names, failed_names).
    """
    service = get_drive_service(connection)
    uploaded, failed = [], []
    for file_name, file_bytes, mime_type in files:
        try:
            _upload(service, folder_id, file_name, file_bytes, mime_type)
            uploaded.append(file_name)
        except DriveAuthExpired:
            raise
        except Exception:
            logger.exception("Drive upload failed for %s", file_name)
            failed.append(file_name)
    return uploaded, failed


def submission_folder_segments(submission, approved_copy=False):
    """
    Folder names from the archive root down:
    Academic Year / Organization / Document Type [/ Approved].

    "Approved" is added only for the approved document of an Accomplishment
    Report (`approved_copy=True`); the report itself stays in the parent folder.
    """
    year, org, doc_type = submission.academic_year_id, submission.org_id, submission.doc_type_id
    segments = [
        year.year if year else "Unspecified Year",
        org.name if org else "Unspecified Organization",
        doc_type.name if doc_type else "Uncategorized",
    ]
    if approved_copy and submission.is_accomplishment_report:
        segments.append(APPROVED_FOLDER_NAME)
    return segments


def resolve_submission_folder_path(connection, submission, approved_copy=False, base_folder_id=None):
    """
    Walks/creates the folder chain for `submission` under connection.folder_id,
    returning (deepest_folder_dict, path_segments).
    """
    segments = submission_folder_segments(submission, approved_copy)
    service = get_drive_service(connection)  # built once for the whole path

    parent_id, folder = base_folder_id or connection.folder_id or None, None
    for segment in segments:
        folder = find_or_create_folder(connection, segment, parent_id=parent_id, service=service)
        parent_id = folder["id"]
    return folder, segments
