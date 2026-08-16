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


def upload_file_to_folder(connection, folder_id, file_name, file_bytes, mime_type):
    service = get_drive_service(connection)
    metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
    uploaded = service.files().create(body=metadata, media_body=media, fields="id, webViewLink").execute()
    return uploaded

def find_or_create_folder(connection, name, parent_id=None):
    """
    Looks for a folder named `name` under `parent_id` (or Drive root if
    parent_id is None). Creates it if it doesn't exist. Returns the folder
    dict {id, name}.
    """
    service = get_drive_service(connection)
    safe_name = name.replace("'", "\\'")
    q = (
        "mimeType = 'application/vnd.google-apps.folder' and trashed = false "
        f"and name = '{safe_name}'"
    )
    q += f" and '{parent_id}' in parents" if parent_id else " and 'root' in parents"

    results = service.files().list(q=q, fields="files(id, name)", pageSize=1).execute()
    files = results.get("files", [])
    if files:
        return files[0]

    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    return service.files().create(body=metadata, fields="id, name").execute()


def resolve_submission_folder_path(connection, submission):
    """
    Walks/creates the Academic Year -> Organization -> Submission Title
    folder chain under connection.folder_id (the staff's configured root),
    returning (deepest_folder_dict, path_segments).
    """
    segments = []
    if submission.academic_year_id:
        segments.append(submission.academic_year_id.year)
    if submission.org_id:
        segments.append(submission.org_id.name)
    if submission.doc_type_id:
        segments.append(submission.doc_type_id.name)
    else:
        segments.append("Uncategorized")

    parent_id = connection.folder_id or None
    folder = None
    for segment in segments:
        folder = find_or_create_folder(connection, segment, parent_id=parent_id)
        parent_id = folder["id"]
    return folder, segments