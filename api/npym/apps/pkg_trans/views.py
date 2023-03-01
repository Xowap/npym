from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urljoin

from django.conf import settings
from django.core.files import File
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from packaging.version import Version as PyVersion
from psqlextra.types import ConflictAction
from wheel_filename import ParsedWheelFilename, parse_wheel_filename

from .models import Archive, Distribution, Version, Download
from .npm import Npm, PackageInfo, version_sem_to_py
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
    distribution = get_object_or_404(Distribution, js_name=node_name)

    return redirect(
        reverse(
            "package",
            kwargs=dict(
                package_name=distribution.python_name,
            ),
        )
    )


@dataclass
class VersionInfo:
    """
    Display information for a version
    """

    url: str
    file_name: str
    hash: str


def package_versions(
    distribution: Distribution, package_info: PackageInfo
) -> Sequence[VersionInfo]:
    """
    As the version mapping between NPM and Python is not guaranteed to be 1:1,
    we need to keep track of what mapping we do so that we don't map two
    different NPM versions to the same Python version.

    This fetches the versions from NPM, looks for archives for each of them,
    stores the new versions found in NPM, computes what has to be displayed,
    etc.
    """

    versions = {}
    out = []

    seen = set()
    to_insert = []

    for js_version in package_info["versions"]:
        try:
            python_version = version_sem_to_py(js_version)
        except ValueError:
            pass
        else:
            if python_version in seen:
                continue

            seen.add(python_version)
            to_insert.append(
                dict(
                    distribution=distribution,
                    python_version=python_version,
                    js_version=js_version,
                )
            )

    Version.objects.on_conflict(
        ["distribution", "python_version"], ConflictAction.NOTHING
    ).bulk_insert(to_insert)

    for arch in Archive.objects.filter(
        version__distribution__js_name=package_info["name"],
        format=Archive.Format.wheel,
        translator=Archive.Translator.v1,
    ):
        versions[arch.version.python_version] = arch

    for version in sorted(
        distribution.versions.values_list("python_version", flat=True),
        key=lambda v: PyVersion(v),
        reverse=True,
    ):
        if version in versions:
            hash_ = versions[version].hash_sha256
        else:
            hash_ = ""

        file_name = distribution.wheel_name(version)

        out.append(
            VersionInfo(
                url=reverse(
                    "archive",
                    kwargs=dict(
                        archive_name=parse_wheel_filename(file_name),
                    ),
                ),
                file_name=file_name,
                hash=hash_,
            )
        )

    return out


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

    npm = Npm()

    package_info = npm.get_package_info(distribution.js_name)

    if (desc := package_info.get("description", "")) != distribution.description:
        distribution.description = desc
        distribution.save(update_fields=["description"])

    return render(
        request,
        "pkg_trans/package.html",
        context=dict(
            distribution=distribution,
            package_versions=package_versions(distribution, package_info),
        ),
    )


def make_archive(package_name: str, python_version: str) -> Archive:
    """
    Actually calls the translation logic to transform the NPM package into an
    installable Python package. This package is then stored and ready to be
    served by archive().
    """

    npm = Npm()
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
    package_info = npm.get_package_info(distribution.js_name)

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


def archive(request: HttpRequest, archive_name: ParsedWheelFilename) -> FileResponse:
    """
    Tries to find the required archive (which we know from name parsing) and
    translates the NPM package if required.

    For now we just stream the thing from storages, that's not super scalable
    but let's see how we do it in the future.
    """

    package_name = archive_name.project.replace("_", "-")

    arch = Archive.objects.filter(
        version__distribution__python_name_searchable=package_name,
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
