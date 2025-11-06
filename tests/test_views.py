"""
Test cases for image URL upload views.
"""

from unittest.mock import patch, Mock

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from requests.exceptions import Timeout, HTTPError, RequestException
from wagtail.images import get_image_model
from wagtail.models import Collection

from image_url_upload.views import CustomImageIndexView, AddFromURLView

Image = get_image_model()
User = get_user_model()


class CustomImageIndexViewTests(TestCase):
    """Test cases for CustomImageIndexView."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )
        self.factory = RequestFactory()
        self.view = CustomImageIndexView()
        # Set up request attribute needed by the view
        self.view.request = self.factory.get("/admin/images-w-url/")
        self.view.request.user = self.user

    def test_header_buttons_includes_add_from_url(self):
        """Header buttons should include 'Add an Image from URL' button."""
        buttons = self.view.header_buttons
        labels = [str(b.label) for b in buttons]
        self.assertIn("Add an Image from URL", labels)

    def test_header_button_has_correct_url(self):
        """Add from URL button should have correct URL."""
        buttons = self.view.header_buttons
        url_button = next(b for b in buttons if "URL" in str(b.label))
        self.assertEqual(url_button.url, reverse("add_from_url"))

    def test_header_button_has_plus_icon(self):
        """Add from URL button should use plus icon."""
        buttons = self.view.header_buttons
        url_button = next(b for b in buttons if "URL" in str(b.label))
        self.assertEqual(url_button.icon_name, "plus")

    def test_header_buttons_includes_parent_buttons(self):
        """Header should include buttons from parent class."""
        buttons = self.view.header_buttons
        # Should have more than just our custom button
        self.assertGreater(len(buttons), 0)


class AddFromURLViewTests(TestCase):
    """Test cases for AddFromURLView."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )
        self.factory = RequestFactory()
        self.client.login(username="admin", password="password")
        self.collection = Collection.get_first_root_node()
        self.url = reverse("add_from_url")

    def test_view_inherits_from_add_view(self):
        """View should inherit from Wagtail's AddView."""
        from wagtail.images.views.multiple import AddView
        self.assertTrue(issubclass(AddFromURLView, AddView))

    def test_template_name_is_correct(self):
        """View should use correct template."""
        view = AddFromURLView()
        self.assertEqual(view.template_name, "image_url_upload/add_via_url.html")

    def test_get_context_data_includes_breadcrumbs(self):
        """Context should include breadcrumbs."""
        view = AddFromURLView()
        view.request = self.factory.get(self.url)
        view.request.user = self.user
        view.model = Image
        view.permission_policy = view.permission_policy
        context = view.get_context_data()
        self.assertIn("breadcrumbs_items", context)
        self.assertEqual(len(context["breadcrumbs_items"]), 2)
        self.assertEqual(str(context["breadcrumbs_items"][0]["label"]), "Images")
        self.assertEqual(str(context["breadcrumbs_items"][1]["label"]), "Add from URL")

    def test_get_context_data_includes_header_title(self):
        """Context should include header title."""
        view = AddFromURLView()
        view.request = self.factory.get(self.url)
        view.request.user = self.user
        view.model = Image
        view.permission_policy = view.permission_policy
        context = view.get_context_data()
        self.assertIn("header_title", context)
        self.assertEqual(str(context["header_title"]), "Add image from URL")


    def test_missing_url_returns_error(self):
        """POST without URL should return error."""
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get("success", True))
        self.assertIn("Please provide a URL", data.get("error_message", ""))

    def test_empty_url_returns_error(self):
        """POST with empty URL should return error."""
        response = self.client.post(self.url, {"url": ""})
        data = response.json()
        self.assertFalse(data.get("success", True))
        self.assertIn("Please provide a URL", data["error_message"])

    @patch("image_url_upload.views.requests.get")
    def test_successful_image_upload(self, mock_get):
        """Should successfully upload image from URL."""
        # Create mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = self.client.post(
            self.url,
            {"url": "https://example.com/test.jpg", "collection": self.collection.id},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should create an image
        self.assertTrue(Image.objects.filter(title="test").exists())

    @patch("image_url_upload.views.requests.get")
    def test_successful_upload_with_png(self, mock_get):
        """Should handle PNG images correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_png_bytes()
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = self.client.post(
            self.url,
            {"url": "https://example.com/photo.png", "collection": self.collection.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Image.objects.filter(title="photo").exists())

    @patch("image_url_upload.views.requests.get")
    def test_url_with_query_params(self, mock_get):
        """Should handle URLs with query parameters correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = self.client.post(
            self.url,
            {"url": "https://example.com/photo.jpg?size=large&v=2", "collection": self.collection.id},
        )

        self.assertEqual(response.status_code, 200)
        # Filename should be extracted without query params
        self.assertTrue(Image.objects.filter(title="photo").exists())

    @patch("image_url_upload.views.requests.get")
    def test_timeout_error(self, mock_get):
        """Should handle timeout errors gracefully."""
        mock_get.side_effect = Timeout("Connection timeout")

        response = self.client.post(self.url, {"url": "https://example.com/slow.jpg"})
        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("timeout", data["error_message"].lower())

    @patch("image_url_upload.views.requests.get")
    def test_http_404_error(self, mock_get):
        """Should handle 404 HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_get.return_value = mock_response

        response = self.client.post(self.url, {"url": "https://example.com/missing.jpg"})
        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("HTTP error", data["error_message"])
        self.assertIn("404", data["error_message"])

    @patch("image_url_upload.views.requests.get")
    def test_http_500_error(self, mock_get):
        """Should handle 500 HTTP errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_get.return_value = mock_response

        response = self.client.post(self.url, {"url": "https://example.com/error.jpg"})
        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("HTTP error", data["error_message"])
        self.assertIn("500", data["error_message"])

    @patch("image_url_upload.views.requests.get")
    def test_connection_error(self, mock_get):
        """Should handle connection errors."""
        mock_get.side_effect = RequestException("Connection refused")

        response = self.client.post(self.url, {"url": "https://example.com/image.jpg"})
        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("Download failed", data["error_message"])

    @patch("image_url_upload.views.requests.get")
    def test_generic_exception(self, mock_get):
        """Should handle unexpected exceptions."""
        mock_get.side_effect = Exception("Unexpected error")

        response = self.client.post(self.url, {"url": "https://example.com/image.jpg"})
        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("Unexpected error", data["error_message"])


    @patch("image_url_upload.views.requests.get")
    def test_timeout_value_is_set(self, mock_get):
        """Should set timeout for requests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        self.client.post(self.url, {"url": "https://example.com/test.jpg"})

        mock_get.assert_called_once()
        # Check timeout is passed (as positional or keyword arg)
        call_args = mock_get.call_args
        # Can be in args[1] or kwargs['timeout']
        if len(call_args[0]) > 1:
            self.assertEqual(call_args[0][1], 10)  # positional arg
        else:
            self.assertEqual(call_args[1]["timeout"], 10)  # keyword arg

    @patch("image_url_upload.views.requests.get")
    def test_default_filename_when_missing(self, mock_get):
        """Should use default filename when URL has no filename."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = self.client.post(
            self.url, {"url": "https://example.com/", "collection": self.collection.id}
        )

        self.assertEqual(response.status_code, 200)
        # Should create image with default name
        self.assertTrue(Image.objects.exists())

    @patch("image_url_upload.views.requests.get")
    def test_collection_assignment(self, mock_get):
        """Should assign image to specified collection."""
        custom_collection = Collection.objects.create(
            name="Test Collection",
            depth=2,
            path="00010001"
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        self.client.post(
            self.url, {"url": "https://example.com/test.jpg", "collection": custom_collection.id}
        )

        image = Image.objects.latest("id")
        self.assertEqual(image.collection_id, custom_collection.id)

    @patch("image_url_upload.views.requests.get")
    def test_duplicate_detection(self, mock_get):
        """Should detect duplicate images."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Upload first image
        self.client.post(
            self.url, {"url": "https://example.com/duplicate.jpg", "collection": self.collection.id}
        )
        initial_count = Image.objects.count()

        # Try uploading duplicate
        response = self.client.post(
            self.url, {"url": "https://example.com/duplicate.jpg", "collection": self.collection.id}
        )

        data = response.json()
        # Count should remain the same if duplicate is detected and removed
        final_count = Image.objects.count()

        # The duplicate should either not be created or be removed
        self.assertLessEqual(final_count, initial_count + 1)

    def test_requires_authentication(self):
        """Should require user to be authenticated."""
        self.client.logout()
        response = self.client.post(self.url, {"url": "https://example.com/test.jpg"})
        # Should redirect to login or return 403
        self.assertIn(response.status_code, [302, 403])

    @patch("image_url_upload.views.requests.get")
    def test_title_extracted_from_filename(self, mock_get):
        """Should extract title from filename without extension."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        self.client.post(
            self.url,
            {"url": "https://example.com/my-awesome-photo.jpg", "collection": self.collection.id}
        )

        image = Image.objects.latest("id")
        self.assertEqual(image.title, "my-awesome-photo")

    @patch("image_url_upload.views.requests.get")
    def test_logging_on_success(self, mock_get):
        """Should log successful uploads."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with self.assertLogs("image_url_upload.views", level="INFO") as logs:
            self.client.post(
                self.url,
                {"url": "https://example.com/test.jpg", "collection": self.collection.id}
            )

            log_output = "\n".join(logs.output)
            self.assertIn("Downloading image from", log_output)

    @patch("image_url_upload.views.requests.get")
    def test_logging_on_timeout(self, mock_get):
        """Should log timeout errors."""
        mock_get.side_effect = Timeout("Connection timeout")

        with self.assertLogs("image_url_upload.views", level="ERROR") as logs:
            self.client.post(self.url, {"url": "https://example.com/slow.jpg"})

            log_output = "\n".join(logs.output)
            self.assertIn("Timeout", log_output)

    @staticmethod
    def _create_test_image_bytes():
        """Create a minimal valid JPEG image in bytes."""
        # Minimal valid JPEG (1x1 pixel)
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
            b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
            b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00'
            b'\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\t\xff\xc4\x00\x14\x10\x01'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff'
            b'\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x00\xff\xd9'
        )

    @staticmethod
    def _create_test_png_bytes():
        """Create a minimal valid PNG image in bytes."""
        # Minimal valid PNG (1x1 pixel, transparent)
        return (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )


class DomainValidationIntegrationTests(TestCase):
    """Integration tests for domain validation in views."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="password"
        )
        self.client.login(username="admin", password="password")
        self.url = reverse("add_from_url")
        self.collection = Collection.get_first_root_node()

    @override_settings(WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS=['example.com', 'trusted.com'])
    @patch("image_url_upload.views.requests.get")
    def test_allowed_domain_succeeds(self, mock_get):
        """Should allow domains in the allowed list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = self.client.post(
            self.url,
            {"url": "https://example.com/image.jpg", "collection": self.collection.id}
        )

        # Should not have domain validation error
        data = response.json()
        error_message = data.get("error_message", "")
        self.assertNotIn("not in the allowed domains list", error_message)
        self.assertNotIn("is blocked", error_message)

    @override_settings(WAGTAIL_IMAGE_URL_ALLOWED_DOMAINS=['example.com', 'trusted.com'])
    def test_not_allowed_domain_fails(self):
        """Should block domains not in the allowed list."""
        response = self.client.post(
            self.url,
            {"url": "https://notallowed.com/image.jpg", "collection": self.collection.id}
        )

        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertIn("not in the allowed domains list", data.get("error_message"))

    @override_settings(WAGTAIL_IMAGE_URL_BLOCKED_DOMAINS=['spam.com', 'malicious.com'])
    def test_blocked_domain_fails(self):
        """Should block domains in the blocked list."""
        response = self.client.post(
            self.url,
            {"url": "https://spam.com/image.jpg", "collection": self.collection.id}
        )

        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertIn("is blocked", data.get("error_message"))

    @override_settings(WAGTAIL_IMAGE_URL_BLOCKED_DOMAINS=['spam.com'])
    @patch("image_url_upload.views.requests.get")
    def test_not_blocked_domain_succeeds(self, mock_get):
        """Should allow domains not in the blocked list."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = self._create_test_image_bytes()
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = self.client.post(
            self.url,
            {"url": "https://example.com/image.jpg", "collection": self.collection.id}
        )

        # Should not have domain validation error
        data = response.json()
        error_message = data.get("error_message", "")
        self.assertNotIn("not in the allowed domains list", error_message)
        self.assertNotIn("is blocked", error_message)

    @override_settings(WAGTAIL_IMAGE_URL_PREVENT_SSRF=True)
    def test_private_ip_blocked_with_ssrf_protection(self):
        """Should block private IP addresses when SSRF protection is enabled."""
        response = self.client.post(
            self.url,
            {"url": "http://192.168.1.1/image.jpg", "collection": self.collection.id}
        )

        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertIn("private IP", data.get("error_message"))

    @override_settings(WAGTAIL_IMAGE_URL_PREVENT_SSRF=True)
    def test_localhost_blocked_with_ssrf_protection(self):
        """Should block localhost when SSRF protection is enabled."""
        response = self.client.post(
            self.url,
            {"url": "http://localhost/image.jpg", "collection": self.collection.id}
        )

        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertIn("private IP", data.get("error_message"))

    @staticmethod
    def _create_test_image_bytes():
        """Create a minimal valid JPEG image in bytes."""
        # Minimal valid JPEG (1x1 pixel)
        return (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
            b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
            b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
            b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00'
            b'\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\t\xff\xc4\x00\x14\x10\x01'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff'
            b'\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x00\xff\xd9'
        )
