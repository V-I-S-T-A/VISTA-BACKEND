from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import Organization
from .views import OrganizationViewSet


class OrganizationPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Organization.objects.bulk_create([
            Organization(name=f"Organization {i}", acronym=f"ORG{i}",
                         description=f"Description {i}", is_active=i % 2 == 0)
            for i in range(41)
        ])
        # A deterministic secondary sort must also handle identical timestamps.
        Organization.objects.update(created_at=timezone.now())

    def get_page(self, **params):
        request = APIRequestFactory().get("/organizations/", {"page_size": 8, **params})
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True))
        return OrganizationViewSet.as_view({"get": "list"})(request)

    def test_all_pages_are_reachable_with_constant_query_count(self):
        seen = set()
        for page in range(1, 7):
            # Exactly one COUNT and one bounded SELECT, with no per-row queries.
            with self.assertNumQueries(2):
                response = self.get_page(page=page)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 41)
            self.assertEqual(response.data["total_pages"], 6)
            self.assertEqual(len(response.data["results"]), 8 if page < 6 else 1)
            ids = {item["org_id"] for item in response.data["results"]}
            self.assertFalse(seen & ids)
            seen.update(ids)
        self.assertEqual(len(seen), 41)

    def test_status_filter_applies_before_pagination(self):
        response = self.get_page(is_active="false", page=3)
        self.assertEqual(response.data["count"], 20)
        self.assertEqual(len(response.data["results"]), 4)
        self.assertTrue(all(not item["is_active"] for item in response.data["results"]))

    def test_search_matches_description_and_partial_id_across_the_dataset(self):
        target = Organization.objects.get(acronym="ORG40")
        for search in ("Description 40", str(target.org_id)[:8], "ORG40"):
            with self.subTest(search=search):
                response = self.get_page(query=search)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["count"], 1)
                self.assertEqual(str(response.data["results"][0]["org_id"]), str(target.org_id))
