"""
Views for image URL upload functionality.
"""

import logging
import os

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from wagtail.admin.widgets.button import HeaderButton
from wagtail.images.views.images import IndexView as ImageIndexView
from wagtail.images.views.multiple import AddView

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/webp",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB in bytes

logger = logging.getLogger(__name__)


class CustomImageIndexView(ImageIndexView):
    """
    Custom image index view with additional "Add from URL" button.

    This extends the default Wagtail image index view to add a button
    for importing images from URLs.
    """

    @property
    def header_buttons(self):
        """Add custom header button for URL upload."""
        buttons = super().header_buttons

        buttons.append(
            HeaderButton(
                label=_("Add an Image from URL"),
                url=reverse("add_from_url"),
                icon_name="plus",
            )
        )

        return buttons


class AddFromURLView(AddView):
    """
    AJAX view for bulk image upload from URLs.

    This view handles POST requests containing image URLs and creates
    Wagtail Image objects. It extends Wagtail's AddView to leverage
    built-in duplicate detection and form validation.
    """

    template_name = "image_url_upload/add_via_url.html"

    def get_context_data(self, **kwargs):
        """Add breadcrumbs and header to context."""
        context = super().get_context_data(**kwargs)
        context["breadcrumbs_items"] = [
            {"url": reverse("images_w_url_index"), "label": _("Images")},
            {"url": "", "label": _("Add from URL")},
        ]
        context["header_title"] = _("Add image from URL")
        return context

    def post(self, request):
        """
        Handle image upload from URL.

        Args:
            request: The HTTP request containing 'url' and optional 'collection'

        Returns:
            JsonResponse with success/error status and image data
        """
        image_url = request.POST.get("url")

        if not image_url:
            return JsonResponse(
                {
                    "success": False,
                    "error_message": _("Please provide a URL."),
                }
            )

        try:
            # Download the image data
            logger.info(f"Downloading image from: {image_url}")
            response = requests.get(
                image_url, timeout=10, headers={"User-Agent": "Wagtail-Image-From-URL/0.1.0"}
            )
            response.raise_for_status()

            # Validate content type
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                logger.warning(f"Invalid content type for {image_url}: {content_type}")
                return JsonResponse(
                    {
                        "success": False,
                        "error_message": _("Invalid file type. Allowed types: JPEG, PNG, GIF, BMP, WEBP."),
                    }
                )

            # Validate file size
            file_size = len(response.content)
            if file_size > MAX_FILE_SIZE:
                logger.warning(f"File too large for {image_url}: {file_size} bytes")
                return JsonResponse(
                    {
                        "success": False,
                        "error_message": _("File size exceeds maximum allowed size of {size} MB.").format(
                            size=MAX_FILE_SIZE // (1024 * 1024)
                        ),
                    }
                )

            if file_size == 0:
                logger.warning(f"Empty file downloaded from {image_url}")
                return JsonResponse(
                    {
                        "success": False,
                        "error_message": _("The downloaded file is empty."),
                    }
                )

            # Extract filename from URL
            filename = os.path.basename(image_url.split("?")[0]) or "image.jpg"

            # Wrap in Django file object
            file = SimpleUploadedFile(
                name=filename,
                content=response.content,
                content_type=content_type,
            )

            # Use Wagtail's upload form for validation
            upload_form_class = self.get_upload_form_class()
            form = upload_form_class(
                data={
                    "title": os.path.splitext(filename)[0],
                    "collection": request.POST.get("collection", 1),
                },
                files={"file": file},
                user=request.user,
            )

            if form.is_valid():
                # Save using Wagtail's method (includes duplicate checking)
                self.object = self.save_object(form)

                # Get response data (includes duplicate info)
                response_data = self.get_edit_object_response_data()

                # If duplicate detected, remove the newly created object
                if response_data.get("duplicate"):
                    logger.info(f"Duplicate image detected: {image_url}")
                    self.object.delete()
                else:
                    logger.info(f"Image uploaded successfully: {self.object.title}")

                return JsonResponse(response_data)
            else:
                # Return form validation errors
                logger.warning(f"Form validation failed for {image_url}: {form.errors}")
                return JsonResponse(self.get_invalid_response_data(form))

        except requests.exceptions.Timeout:
            logger.error(f"Timeout downloading image from {image_url}")
            return JsonResponse(
                {
                    "success": False,
                    "error_message": _("Request timeout - the server took too long to respond."),
                }
            )
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error downloading {image_url}: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error_message": _("HTTP error: {status}").format(status=e.response.status_code),
                }
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed for {image_url}: {e}")
            return JsonResponse(
                {
                    "success": False,
                    "error_message": _("Download failed: {error}").format(error=str(e)),
                }
            )
        except Exception as e:
            logger.exception(f"Unexpected error processing {image_url}")
            return JsonResponse(
                {
                    "success": False,
                    "error_message": _("Unexpected error: {error}").format(error=str(e)),
                }
            )
