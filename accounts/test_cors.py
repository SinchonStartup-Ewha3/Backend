from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class SocialLoginCorsTests(APITestCase):
    origin = "https://weether.kr"

    def test_post_response_allows_frontend_origin(self):
        response = self.client.post(
            reverse("social-login"),
            {},
            format="json",
            HTTP_ORIGIN=self.origin,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response["Access-Control-Allow-Origin"], self.origin)

    def test_preflight_allows_frontend_origin(self):
        response = self.client.options(
            reverse("social-login"),
            HTTP_ORIGIN=self.origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Access-Control-Allow-Origin"], self.origin)
        self.assertIn("POST", response["Access-Control-Allow-Methods"])
        self.assertIn("OPTIONS", response["Access-Control-Allow-Methods"])
        self.assertIn(
            "content-type",
            response["Access-Control-Allow-Headers"].lower(),
        )

    def test_preflight_rejects_unlisted_origin(self):
        response = self.client.options(
            reverse("social-login"),
            HTTP_ORIGIN="https://example.com",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("Access-Control-Allow-Origin", response)
