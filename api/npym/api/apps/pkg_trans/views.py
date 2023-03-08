from pathlib import Path
from urllib.parse import urljoin

from django.conf import settings
from django.core.files import File
from django.db.transaction import atomic
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from wheel_filename import ParsedWheelFilename

from .models import Archive, Distribution, Download, Version
from .npm import Npm
from .resolver import package_versions
from .translator import PackageTranslator, file_digest


def root(request: HttpRequest) -> HttpResponse:
    """
    Just a landing page of sorts for this application. In theory it should
    be listing all packages available, but there are 2 millions of them and no
    package manager uses this so it's rather pointless for our use case.
    """

    root_url = urljoin(settings.BASE_URL, reverse("root"))

    return render(request, "pkg_trans/root.html", context=dict(root_url=root_url))


def search(request: HttpRequest) -> HttpResponse:
    """
    This allows to search for a NPM package and being redirected to the page of
    the equivalent NPyM package.
    """

    # noinspection PyTypeChecker
    node_name = request.GET.get("q", "")
    distribution = get_object_or_404(
        Distribution, js_name=node_name, generated_for=None
    )

    return redirect(
        reverse(
            "package",
            kwargs=dict(
                package_name=distribution.python_name,
            ),
        )
    )


def package(request: HttpRequest, package_name: str) -> HttpResponse:
    """
    Package information page, mostly used to list all the package's versions
    so that the package manager can pick one.
    """

    try:
        distribution = Distribution.objects.get(python_name=package_name)
    except Distribution.DoesNotExist:
        distribution = get_object_or_404(
            Distribution, python_name_searchable=package_name
        )

        return redirect(
            reverse(
                "package",
                kwargs=dict(
                    package_name=distribution.python_name,
                ),
            )
        )

    npm = Npm.instance()

    package_info = npm.get_package_info(distribution.real.js_name)

    if (desc := package_info.get("description", "")) != distribution.description:
        distribution.description = desc
        distribution.save(update_fields=["description"])

    signature = ""

    if distribution.original is not None:
        _, signature = distribution.python_name.rsplit(".", 1)

    return render(
        request,
        "pkg_trans/package.html",
        context=dict(
            distribution=distribution,
            package_versions=package_versions(distribution, package_info, signature),
        ),
    )


def make_archive(package_name: str, python_version: str) -> Archive:
    """
    Actually calls the translation logic to transform the NPM package into an
    installable Python package. This package is then stored and ready to be
    served by archive().
    """

    npm = Npm.instance()
    distribution = get_object_or_404(
        Distribution,
        python_name_searchable=package_name,
    )
    version = get_object_or_404(
        Version,
        distribution=distribution,
        python_version=python_version,
    )
    js_version = version.js_version
    package_info = npm.get_package_info(distribution.real.js_name)

    try:
        version_info = package_info["versions"][js_version]
    except KeyError:
        raise Http404("Version not found")

    with PackageTranslator(distribution, version, version_info) as wheel_path:
        with open(wheel_path, "rb") as f:
            h = file_digest(f, "sha256")

            f.seek(0)

            return Archive.objects.create(
                version=version,
                archive=File(f, name=Path(wheel_path).name),
                format=Archive.Format.wheel,
                translator=Archive.Translator.v1,
                hash_sha256=h.hexdigest(),
            )


@atomic
def archive(request: HttpRequest, archive_name: ParsedWheelFilename) -> FileResponse:
    """
    Tries to find the required archive (which we know from name parsing) and
    translates the NPM package if required.

    For now we just stream the thing from storages, that's not super scalable
    but let's see how we do it in the future.

    Notes
    -----
    We use the `select_for_update` to lock the distribution row so that we
    don't have two concurrent requests trying to translate the same package.
    While this is not granular to the version at least it works.
    """

    package_name = archive_name.project.replace("_", "-")

    distribution = (
        Distribution.objects.select_for_update()
        .filter(python_name_searchable=package_name)
        .first()
    )

    if not distribution:
        raise Http404("Package not found")

    arch = Archive.objects.filter(
        version__distribution=distribution,
        version__python_version=archive_name.version,
        format=Archive.Format.wheel,
        translator=Archive.Translator.v1,
    ).first()

    if arch is None:
        arch = make_archive(package_name, archive_name.version)

    Download.objects.create(archive=arch)

    return FileResponse(
        arch.archive,
        filename=Path(arch.archive.name).name,
        as_attachment=True,
    )
