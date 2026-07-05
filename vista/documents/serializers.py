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
    class Meta:
        model = Document
        fields = ["document_id", "submission_id", "file_name", "file_url", "mime_type", "file_size_kb"]
        read_only_fields = ["document_id"]

    def create(self, validated_data):
        submission = validated_data["submission_id"]
        latest = Document.objects.filter(submission_id=submission).order_by("-version").first()
        next_version = (latest.version + 1) if latest else 1

        Document.objects.filter(submission_id=submission, is_current=True).update(is_current=False)

        return Document.objects.create(**validated_data, version=next_version, is_current=True)