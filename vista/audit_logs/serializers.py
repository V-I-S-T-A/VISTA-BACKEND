from rest_framework import serializers
from .models import AuditLog

class AuditLogSerializer(serializers.ModelSerializer):
<<<<<<< HEAD
    # CHANGED: Renamed to performed_by to match your React frontend!
    performed_by = serializers.SerializerMethodField()
    performed_by_org = serializers.SerializerMethodField()
=======
    performed_by = serializers.CharField(source="user_id.get_full_name", read_only=True)
    performed_by_email = serializers.CharField(source="user_id.email", read_only=True)
>>>>>>> 6260b982c7d3b013f308bde581ba0af05e5f5044

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
<<<<<<< HEAD
    # CHANGED: Renamed to performed_by to match your React frontend!
    performed_by = serializers.SerializerMethodField()
    performed_by_org = serializers.SerializerMethodField()
=======
    performed_by = serializers.CharField(source="user_id.get_full_name", read_only=True)
    performed_by_email = serializers.CharField(source="user_id.email", read_only=True)
    performed_by_image = serializers.CharField(source="user_id.image_url", read_only=True)
>>>>>>> 6260b982c7d3b013f308bde581ba0af05e5f5044

    class Meta:
        model = AuditLog
        fields = [
            "audit_id",
<<<<<<< HEAD
            "performed_by", # Changed this in the fields list too!
            "performed_by_org",
=======
            "performed_by",
            "performed_by_email",
            "performed_by_image",
            "action",
>>>>>>> 6260b982c7d3b013f308bde581ba0af05e5f5044
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