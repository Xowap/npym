import wheel_filename
from django.urls import path, register_converter

from .views import archive, package, root, search


class WheelFilenameConverter:
    """
    We detect wheel names for the views to get the deduced distribution name,
    version, etc.
    """

    regex = r"[^/]+\.whl"

    def to_python(self, value):
        try:
            return wheel_filename.parse_wheel_filename(value)
        except wheel_filename.InvalidFilenameError:
            raise ValueError("Invalid wheel filename: %r" % value)

    def to_url(self, value):
        return f"{value}"


register_converter(WheelFilenameConverter, "wheel_filename")


urlpatterns = [
    path("", root, name="root"),
    path("-/search/", search, name="search"),
    path(
        "-/archives/<wheel_filename:archive_name>",
        archive,
        name="archive",
    ),
    path("<str:package_name>/", package, name="package"),
]
