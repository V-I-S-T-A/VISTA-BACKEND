from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "document_id", "submission_id", "file_name", "file_url",
            "mime_type", "file_size_kb", "version", "is_current", "uploaded_at",
        ]
        read_only_fields = ["document_id", "version", "is_current", "uploaded_at"]


class DocumentCreateSerializer(serializers.ModelSerializer):
    cloudinary_resource_type = serializers.ChoiceField(choices=('image', 'video', 'raw'), required=False, allow_null=True)

    class Meta:
        model = Document
        fields = ["document_id", "submission_id", "file_name", "file_url", "mime_type", "file_size_kb", "cloudinary_public_id", "cloudinary_resource_type"]
        read_only_fields = ["document_id"]

    def validate(self, attrs):
        if bool(attrs.get('cloudinary_public_id')) != bool(attrs.get('cloudinary_resource_type')):
            raise serializers.ValidationError('Provide both Cloudinary public ID and resource type.')
        return attrs

    def create(self, validated_data):
        submission = validated_data["submission_id"]
        latest = Document.objects.filter(submission_id=submission).order_by("-version").first()
        next_version = (latest.version + 1) if latest else 1

        Document.objects.filter(submission_id=submission, is_current=True).update(is_current=False)

        return Document.objects.create(**validated_data, version=next_version, is_current=True)
