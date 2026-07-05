from .models import AuditLog


def log_action(user, action, table_name, changes=None):
    AuditLog.objects.create(
        user_id=user,
        action=action,
        table_name=table_name,
        changes=changes or {},
    )


def log_create(user, table_name, new_data):
    log_action(user, AuditLog.ACTION_CREATE, table_name, {"new": new_data})


def log_update(user, table_name, old_data, new_data):
    log_action(user, AuditLog.ACTION_UPDATE, table_name, {"old": old_data, "new": new_data})


def log_delete(user, table_name, old_data):
    log_action(user, AuditLog.ACTION_DELETE, table_name, {"deleted": old_data})


def log_login(user):
    log_action(user, AuditLog.ACTION_LOGIN, "tbl_Users")


def log_logout(user):
    log_action(user, AuditLog.ACTION_LOGOUT, "tbl_Users")


def log_status_change(user, table_name, record_id, old_status, new_status):
    log_action(
        user,
        AuditLog.ACTION_STATUS_CHANGE,
        table_name,
        {
            "record_id": str(record_id),
            "old_status": old_status,
            "new_status": new_status,
        },
    )