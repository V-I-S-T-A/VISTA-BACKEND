from django.urls import path

from .views import (
    DriveConnectionView,
    DriveAuthStartView,
    DriveAuthCallbackView,
    DriveFolderListView,
    DriveFolderSelectView,
    DriveFolderCreateView,
    DriveDisconnectView,
)

urlpatterns = [
    path("drive/connection/", DriveConnectionView.as_view(), name="drive-connection"),
    path("drive/auth/start/", DriveAuthStartView.as_view(), name="drive-auth-start"),
    path("drive/auth/callback/", DriveAuthCallbackView.as_view(), name="drive-auth-callback"),
    path("drive/folders/", DriveFolderListView.as_view(), name="drive-folder-list"),
    path("drive/folders/select/", DriveFolderSelectView.as_view(), name="drive-folder-select"),
    path("drive/folders/create/", DriveFolderCreateView.as_view(), name="drive-folder-create"),
    path("drive/disconnect/", DriveDisconnectView.as_view(), name="drive-disconnect"),
]