from rest_framework import serializers
from .models import DocumentType


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ["doc_type_id", "name", "code", "description", "required_fields", "is_active"]
        read_only_fields = ["doc_type_id"]

    def validate_required_fields(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("required_fields must be a JSON object.")
        return value

    def validate_code(self, value):
        if not value:
            return value

        value = value.strip().upper()

        # NOTE: ModelSerializer auto-attaches a UniqueValidator for `code`
        # since the model field has unique=True -- but that validator runs
        # BEFORE this method, against the *raw* (not-yet-uppercased) input.
        # That means "fm-ustp-osa-04b" could slip past the automatic check
        # even if "FM-USTP-OSA-04B" already exists, then collide at the DB
        # level after normalization. Checking explicitly here, against the
        # normalized value, closes that gap.
        qs = DocumentType.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A document type with this code already exists.")

        return value


class DocumentTypeListSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ["doc_type_id", "name", "code", "is_active"]