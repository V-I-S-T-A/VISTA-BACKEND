from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    performed_by = serializers.CharField(source="user_id.full_name", read_only=True)
    performed_by_email = serializers.CharField(source="user_id.email", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "audit_id",
            "user_id",
            "performed_by",
            "performed_by_email",
            "action",
            "table_name",
            "changes",
            "performed_at",
        ]
        read_only_fields = fields


class AuditLogListSerializer(serializers.ModelSerializer):
    performed_by = serializers.CharField(source="user_id.full_name", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "audit_id",
            "performed_by",
            "action",
            "table_name",
            "performed_at",
        ]
        read_only_fields = fields