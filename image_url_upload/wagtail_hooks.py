"""
Wagtail hooks for integrating image URL upload functionality.

This module registers custom URLs, views, and menu items with Wagtail's
admin interface.
"""

import logging

from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from .views import CustomImageIndexView, AddFromURLView

logger = logging.getLogger(__name__)


@hooks.register("register_admin_urls")
def register_admin_urls():
    """
    Register admin URLs for image URL upload functionality.

    Returns:
        list: URL patterns for the admin interface
    """
    return [
        path(
            "images/add_from_url/",
            AddFromURLView.as_view(),
            name="add_from_url"
        ),
    ]


@hooks.register("register_admin_urls")
def register_custom_image_index():
    """
    Register the custom image index view with URL upload button.

    Returns:
        list: URL patterns for custom image index
    """
    return [
        path(
            "images-w-url/",
            CustomImageIndexView.as_view(),
            name="images_w_url_index"
        ),
    ]


@hooks.register("register_admin_menu_item")
def register_images_menu_item():
    """
    Register custom Images menu item.

    This replaces the default Images menu item with our custom one
    that includes URL upload functionality.

    Returns:
        MenuItem: The custom images menu item
    """
    return MenuItem(
        _("Images"),
        reverse("images_w_url_index"),
        name="custom_images",
        icon_name="image",
        order=301,
    )


@hooks.register("construct_main_menu")
def hide_default_images_menu_item(request, menu_items):
    """
    Hide the default Images menu item.

    This removes Wagtail's default Images menu item so only our
    custom one (with URL upload functionality) is shown.

    Args:
        request: The HTTP request
        menu_items: List of menu items to modify in-place
    """
    original_count = len(menu_items)
    menu_items[:] = [item for item in menu_items if item.name != "images"]

    if len(menu_items) < original_count:
        logger.debug("Removed default 'images' menu item")
