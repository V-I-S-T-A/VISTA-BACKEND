import django_filters
from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    user_id = django_filters.UUIDFilter(field_name="user_id__user_id")
    action = django_filters.ChoiceFilter(choices=AuditLog.ACTION_CHOICES)
    table_name = django_filters.CharFilter(field_name="table_name", lookup_expr="iexact")
    performed_after = django_filters.DateTimeFilter(field_name="performed_at", lookup_expr="gte")
    performed_before = django_filters.DateTimeFilter(field_name="performed_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ["user_id", "action", "table_name", "performed_after", "performed_before"]