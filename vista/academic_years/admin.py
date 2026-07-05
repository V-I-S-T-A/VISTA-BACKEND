from django.contrib import admin
from .models import AcademicYear


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("year", "created_at")
    search_fields = ("year",)
    ordering = ("-year",)
    readonly_fields = ("academic_year_id", "created_at")