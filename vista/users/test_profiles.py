from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import User


class ProfilePersistenceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="profile@example.com", first_name="Alex", last_name="Rivera"
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("auth-me")

    def test_each_role_can_save_and_reload_personal_details(self):
        for role in ("student", "staff", "admin"):
            with self.subTest(role=role):
                self.user.role = role
                self.user.save(update_fields=["role"])
                response = self.client.patch(self.url, {
                    "birth_date": "2000-02-29", "gender": "Non-binary",
                }, format="json")
                self.assertEqual(response.status_code, 200, response.data)
                self.user.refresh_from_db()
                self.assertEqual(self.user.birth_date.isoformat(), "2000-02-29")
                self.assertEqual(self.user.gender, "Non-binary")
                reloaded = self.client.get(self.url)
                self.assertEqual(reloaded.data["birth_date"], "2000-02-29")
                self.assertEqual(reloaded.data["gender"], "Non-binary")

    def test_self_description_and_prefer_not_to_say_are_saved(self):
        for gender in ("Genderqueer", "Prefer not to say", ""):
            response = self.client.patch(self.url, {"gender": gender}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.user.refresh_from_db()
            self.assertEqual(self.user.gender, gender)

    def test_invalid_or_future_dates_and_overlong_gender_are_rejected(self):
        for payload in (
            {"birth_date": "2001-02-29"},
            {"birth_date": (timezone.localdate() + timedelta(days=1)).isoformat()},
            {"gender": "x" * 101},
        ):
            response = self.client.patch(self.url, payload, format="json")
            self.assertEqual(response.status_code, 400, response.data)

    def test_json_can_clear_optional_details(self):
        self.user.birth_date = "2000-01-01"
        self.user.gender = "Agender"
        self.user.save()
        response = self.client.patch(self.url, {"birth_date": None, "gender": ""}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.birth_date)
        self.assertEqual(self.user.gender, "")

    @patch("users.serializers.cloudinary.uploader.upload", return_value={"secure_url": "https://example.com/avatar.gif"})
    def test_avatar_upload_can_also_clear_optional_details(self, upload):
        self.user.birth_date = "2000-01-01"
        self.user.gender = "Agender"
        self.user.save()
        image = SimpleUploadedFile(
            "avatar.gif",
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )
        response = self.client.patch(self.url, {
            "birth_date": "", "gender": "", "image": image,
        }, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.birth_date)
        self.assertEqual(self.user.gender, "")
        upload.assert_called_once()


class UserManagementScopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="admin@example.com", first_name="Admin", last_name="User", role="admin"
        )
        self.client.force_authenticate(self.admin)
        User.objects.bulk_create([
            User(email=f"student{i}@example.com", first_name="Student", last_name=str(i))
            for i in range(51)
        ])
        self.staff = User.objects.create_user(
            email="staff@example.com", first_name="Staff", last_name="User", role="staff"
        )

    def test_admin_excluded_before_pagination_and_count(self):
        response = self.client.get(reverse("user-list"), {"exclude_admin": "true", "page_size": 50})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 52)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertTrue(all(user["role"] != "admin" for user in response.data["results"]))
        self.assertNotIn("birth_date", response.data["results"][0])
        self.assertNotIn("gender", response.data["results"][0])

    def test_search_and_role_filters_keep_admin_excluded(self):
        for extra in ({"search": "admin@example.com"}, {"role": "admin"}):
            response = self.client.get(reverse("user-list"), {"exclude_admin": "true", **extra})
            self.assertEqual(response.data["count"], 0)
        response = self.client.get(reverse("user-list"), {"exclude_admin": "true", "role": "staff"})
        self.assertEqual(response.data["count"], 1)

    def test_normal_user_lookup_and_own_profile_still_work(self):
        response = self.client.get(reverse("user-detail", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("auth-me")).status_code, 200)

    @patch("users.views.generate_user_list_pdf")
    def test_export_uses_same_exclusion(self, generate_pdf):
        from io import BytesIO
        generate_pdf.return_value = BytesIO(b"%PDF-test")
        response = self.client.get(reverse("user-export-list"), {"exclude_admin": "true"})
        self.assertEqual(response.status_code, 200)
        users = generate_pdf.call_args.args[0]
        self.assertEqual(len(users), 52)
        self.assertTrue(all(user.role != "admin" for user in users))
        response.close()
