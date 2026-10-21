import django_filters
from .models import User


class UserFilter(django_filters.FilterSet):
    exclude_admin = django_filters.BooleanFilter(method="filter_exclude_admin")
    role = django_filters.ChoiceFilter(choices=User.ROLE_CHOICES)
    is_active = django_filters.BooleanFilter()
    org_id = django_filters.UUIDFilter(field_name="org_id__org_id")
    created_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    def filter_exclude_admin(self, queryset, name, value):
        return queryset.exclude(role="admin") if value else queryset

    class Meta:
        model = User
        fields = ["role", "is_active", "org_id", "created_after", "created_before"]