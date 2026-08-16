import io
from datetime import datetime, timezone

from django.conf import settings
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES_CREATE_ONLY = ["https://www.googleapis.com/auth/drive.file"]
SCOPES_FULL = ["https://www.googleapis.com/auth/drive"]


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
        creds.refresh(Request())
        connection.access_token = creds.token
        connection.token_expiry = creds.expiry.replace(tzinfo=timezone.utc)
        connection.save(update_fields=["_access_token", "token_expiry", "updated_at"])

    return creds


def get_drive_service(connection):
    creds = credentials_from_connection(connection)
    return build("drive", "v3", credentials=creds)


def list_folders(connection, query=None):
    service = get_drive_service(connection)
    q = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if query:
        q += f" and name contains '{query}'"
    results = service.files().list(q=q, fields="files(id, name)", pageSize=50).execute()
    return results.get("files", [])


def create_folder(connection, name):
    service = get_drive_service(connection)
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=metadata, fields="id, name").execute()
    return folder

def find_or_create_subfolder(connection, parent_id, name):
    """
    Looks for a folder named `name` directly under `parent_id`. If found,
    returns its id. If not found, creates it and returns the new id.
    Idempotent -- safe to call repeatedly for the same path segment without
    creating duplicate folders on repeated syncs.
    """
    service = get_drive_service(connection)
    safe_name = name.replace("'", "\\'")
    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false "
        f"and name = '{safe_name}' "
        f"and '{parent_id}' in parents"
    )
    results = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id, name").execute()
    return folder["id"]


def ensure_folder_path(connection, base_folder_id, path_segments):
    """
    Ensures a nested folder path exists under base_folder_id, creating any
    missing segments along the way (find-or-create per level, so re-syncing
    the same submission won't create duplicate folder trees). Returns the
    id of the deepest (final) folder in the path.

    path_segments: list of folder names in order, e.g.
        ["2025-2026", "SITE", "Accomplishment Report"]
    """
    current_parent_id = base_folder_id
    for segment in path_segments:
        clean_segment = (segment or "").strip()
        if not clean_segment:
            continue
        current_parent_id = find_or_create_subfolder(connection, current_parent_id, clean_segment)
    return current_parent_id
    """
    Walks/creates a chain of subfolders under `root_folder_id`, one per
    entry in `path_segments` (in order), and returns the final folder's ID.

    Used to build the Academic Year -> Organization -> Document Type
    structure under whichever base folder staff picked/created on the
    GDrive Sync page.
    """
    current_parent_id = root_folder_id
    for raw_segment in path_segments:
        segment = (raw_segment or "").strip()
        if not segment:
            segment = "Unspecified"
        current_parent_id = find_or_create_folder(connection, current_parent_id, segment)
    return current_parent_id

def upload_file_to_folder(connection, folder_id, file_name, file_bytes, mime_type):
    service = get_drive_service(connection)
    metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
    uploaded = service.files().create(body=metadata, media_body=media, fields="id, webViewLink").execute()
    return uploaded