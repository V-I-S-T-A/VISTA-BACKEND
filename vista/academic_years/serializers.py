from rest_framework import serializers
from .models import AcademicYear


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ["academic_year_id", "year", "created_at", "is_active"]
        read_only_fields = ["academic_year_id", "created_at", "is_active"]

    def validate_year(self, value):
        return value.strip()