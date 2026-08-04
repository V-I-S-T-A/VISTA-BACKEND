from rest_framework import serializers
from .models import AuditLog

class AuditLogSerializer(serializers.ModelSerializer):
    # Use SerializerMethodField so Django knows to look for the get_... functions below
    performed_by = serializers.SerializerMethodField()
    performed_by_org = serializers.SerializerMethodField()
    
    # Standard CharFields are fine for direct relationships
    performed_by_email = serializers.CharField(source="user_id.email", read_only=True, default="System User")
    performed_by_image = serializers.CharField(source="user_id.image_url", read_only=True, allow_null=True, default=None)

    class Meta:
        model = AuditLog
        fields = "__all__"

    def get_performed_by(self, obj):
        if obj.user_id:
            name = obj.user_id.get_full_name()
            return name if name else obj.user_id.email
        return "System"

    def get_performed_by_org(self, obj):
        if obj.user_id:
            if obj.user_id.org_id:
                return obj.user_id.org_id.name
            
            # If the user has no organization, check their role!
            if obj.user_id.role == "admin":
                return "System Administrator"
            elif obj.user_id.role == "staff":
                return "OSA Staff"
            
            return "System User"
            
        return "Automated Process"


class AuditLogListSerializer(serializers.ModelSerializer):
    # Use SerializerMethodField so Django knows to look for the get_... functions below
    performed_by = serializers.SerializerMethodField()
    performed_by_org = serializers.SerializerMethodField()
    
    # Standard CharFields are fine for direct relationships
    performed_by_email = serializers.CharField(source="user_id.email", read_only=True, default="System User")
    performed_by_image = serializers.CharField(source="user_id.image_url", read_only=True, allow_null=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "audit_id",
            "performed_by",
            "performed_by_email",
            "performed_by_image",
            "performed_by_org",
            "table_name",
            "action",
            "performed_at",
        ]

    def get_performed_by(self, obj):
        if obj.user_id:
            name = obj.user_id.get_full_name()
            return name if name else obj.user_id.email
        return "System"

    def get_performed_by_org(self, obj):
        if obj.user_id:
            if obj.user_id.org_id:
                return obj.user_id.org_id.name
                
            # If the user has no organization, check their role!
            if obj.user_id.role == "admin":
                return "System Administrator"
            elif obj.user_id.role == "staff":
                return "OSA Staff"
                
            return "System User"
            
        return "Automated Process"


class AuditLogCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"