from rest_framework import serializers
from .models import DocumentType


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ["doc_type_id", "name", "description", "required_fields", "is_active"]
        read_only_fields = ["doc_type_id"]

    def validate_required_fields(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("required_fields must be a JSON object.")
        return value


class DocumentTypeListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ["doc_type_id", "name", "is_active"]