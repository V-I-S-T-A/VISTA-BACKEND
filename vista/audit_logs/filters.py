import django_filters
from django.db.models import Q, Value
from django.db.models.functions import Concat
from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    query = django_filters.CharFilter(method="filter_query")
    user_id = django_filters.UUIDFilter(field_name="user_id__user_id")
    action = django_filters.ChoiceFilter(choices=AuditLog.ACTION_CHOICES)
    table_name = django_filters.CharFilter(field_name="table_name", lookup_expr="iexact")
    performed_after = django_filters.DateTimeFilter(field_name="performed_at", lookup_expr="gte")
    performed_before = django_filters.DateTimeFilter(field_name="performed_at", lookup_expr="lte")
    performed_until = django_filters.DateTimeFilter(field_name="performed_at", lookup_expr="lt")

    def filter_query(self, queryset, name, value):
        queryset = queryset.alias(actor_name=Concat("user_id__first_name", Value(" "), "user_id__last_name"))
        matches = (
            Q(actor_name__icontains=value) | Q(user_id__email__icontains=value)
            | Q(action__icontains=value) | Q(audit_id__icontains=value)
            | Q(table_name__icontains=value)
        )
        if value.lower() in "system/unknown":
            matches |= Q(user_id__isnull=True)
        return queryset.filter(matches)

    class Meta:
        model = AuditLog
        fields = ["user_id", "action", "table_name", "performed_after", "performed_before"]
