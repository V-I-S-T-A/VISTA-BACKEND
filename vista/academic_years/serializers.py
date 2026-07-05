from rest_framework import serializers
from .models import AcademicYear


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ["academic_year_id", "year", "created_at"]
        read_only_fields = ["academic_year_id", "created_at"]

    def validate_year(self, value):
        return value.strip()