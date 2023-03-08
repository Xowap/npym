import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from logging import getLogger
from typing import Dict, MutableMapping, Sequence, TypedDict
from urllib.parse import quote

import httpx
import json_stream.httpx
from django.conf import settings
from packaging.version import Version as PyVersion
from semver import VersionInfo as SemVersion

from .iter import ChunkIterator
from .models import Distribution

PACKAGE_RE = re.compile(r"^(@(?P<org>[^/]+)/)?(?P<package>.+)$")
PACKAGE_NON_CHAR = re.compile(r"[^a-zA-Z0-9]+")
PACKAGE_NUMERIC_BITS = re.compile(r"(?P<prefix>^|-)(?P<number>[0-9])")

logger = getLogger(__name__)


class PackageInfo(TypedDict):
    """
    Very shorted description of what NPM returns when you ask for a specific
    package's metadata.
    """

    name: str
    description: str
    versions: Dict[str, Dict[str, str]]


@dataclass
class NormName:
    """
    Node names need to be analyzed and decomposed. Mostly to know both the
    name of the organization if any (because it's separated differently) and
    the original name so that we can compute things from that.
    """

    package: str
    org: str = ""
    original_package: str = field(compare=False, default="")
    original_org: str = field(compare=False, default="")

    def __post_init__(self):
        """
        Some packages have shitty names that can't translate into Python, in
        those cases we just go for "undefined" and let the de-duplication
        mechanism of the names import do the job of finding them a unique
        name (a beautiful "undefined.1" or something).
        """

        if self.original_org and not self.org:
            self.org = "undefined"

        if not self.package:
            self.package = "undefined"

    def make_safe_py_name(self, name: str):
        """
        Makes sure that a name is safe to become a Python package name. It
        cannot start with a number.

        Parameters
        ----------
        name
            Name you want to transform into a Python package
        """

        if not name:
            return name

        if name[0].isdigit():
            name = f"n{name}"

        return name

    @property
    def safe_org(self):
        """
        An org name that can be a valid package name
        """

        return self.make_safe_py_name(self.org)

    @property
    def safe_package(self):
        """
        A Node package name that can be a valid Python package name
        """

        return self.make_safe_py_name(self.package)

    @property
    def py_name(self):
        """
        Theoretical Python name for this package (could be changed due to
        de-duplication phases).
        """

        if self.org:
            return f"{settings.NPYM_PREFIX}.{self.safe_org}.{self.safe_package}"

        return f"{settings.NPYM_PREFIX}.{self.safe_package}"


def _norm_py_name(package_name: str) -> str:
    """
    Transforms all non-letter characters into dashes, and removes any
    leading or trailing dashes. This should produce a valid Python
    distribution name.
    """

    package_name = package_name.lower()
    package_name = PACKAGE_NON_CHAR.sub("-", package_name)
    package_name = package_name.strip("-")

    return package_name


def searchable_py_name(package_name: str) -> str:
    """
    In order to make a Python name searchable, we go through the normal
    normalization process but instead of having "-", "_" and "." as special
    characters, we only keep "-" which is the way package managers apparently
    normalize requests.
    """

    package_name = _norm_py_name(package_name)
    package_name = package_name.replace("_", "-")
    package_name = package_name.replace(".", "-")

    return package_name


def importable_py_name(package_name: str) -> str:
    """
    Transforms a Python distribution name into something that looks more like
    a module name.

    Parameters
    ----------
    package_name
        Name of the Python distribution
    """

    package_name = package_name.replace("-", "_")

    return package_name


def version_sem_to_py(version: str) -> str:
    """
    Converts as best as possible a SemVer version into a Python version (the
    mapping works in most cases, especially outside weird pre-release naming
    schemes).
    """

    sem = SemVersion.parse(version)
    py = PyVersion(f"{sem.finalize_version()}{sem.prerelease or ''}{sem.build or ''}")

    return f"{py}"


class Npm:
    """
    Utility to access NPM data
    """

    _instance = None
    NAMES_JSON = "https://raw.githubusercontent.com/nice-registry/all-the-package-names/master/names.json"

    def __init__(self):
        self.client = httpx.Client(base_url="https://registry.npmjs.org/")
        self.async_client = None

    @classmethod
    def instance(cls):
        if not cls._instance:
            cls._instance = cls()

        return cls._instance

    def renew_async_client(self):
        """
        You can't have just one async client if you're going to change the
        loop (which we are as we create a new loop every time we use the
        client).
        """

        self.async_client = httpx.AsyncClient(base_url="https://registry.npmjs.org/")

    def get_package_info(self, package_name: str) -> PackageInfo:
        """
        Retrieves the information about a specific package
        """

        response = self.client.get(f"/{quote(package_name)}")
        response.raise_for_status()

        return response.json()

    async def async_get_package_info(self, package_name: str) -> PackageInfo:
        """
        Retrieves the information about a specific package
        """

        response = await self.async_client.get(f"/{quote(package_name)}")
        response.raise_for_status()

        return response.json()

    def _make_norm_name(self, package_name: str) -> NormName:
        """
        Generates the normalized name for a given package, which is useful
        for the names importation procedure.
        """

        package_name = package_name.lower()
        m = PACKAGE_RE.match(package_name)

        org = m.group("org") or ""
        package = m.group("package")

        return NormName(
            package=_norm_py_name(package),
            org=_norm_py_name(org),
            original_package=package,
            original_org=org,
        )

    def _insert_distributions(self, to_add: Sequence[Dict]) -> None:
        """
        We've received a bulk of names that we've normalized, now we need to
        figure out which ones have conflicts (either from the DB or from the
        names we're trying to insert) and resolve them.

        Basically, any two packages that get normalized the same way in Python
        will receive sequential numbers (foo, foo.1, foo.2, etc). It is stored
        in DB so that the order can be kept through time.
        """

        names_index: MutableMapping[str, MutableMapping[str, bool]] = defaultdict(dict)

        conflicts_from_db = Distribution.objects.filter(
            python_name_base__in=[searchable_py_name(d["python_name"]) for d in to_add],
            generated_for=None,
        ).order_by("dedup_seq")
        present_names = set()

        for conflict in conflicts_from_db:
            names_index[conflict.python_name_base][conflict.js_name] = True
            present_names.add(conflict.js_name)

        for distribution in to_add:
            names_index[searchable_py_name(distribution["python_name"])][
                distribution["js_name"]
            ] = True

        to_add_real = []

        for python_name, js_names in names_index.items():
            if len(js_names) > 1:
                logger.debug(f"Found conflict for {python_name}: {list(js_names)}")

            for i, js_name in enumerate(js_names):
                if js_name in present_names:
                    continue

                norm = self._make_norm_name(js_name)

                if i == 0:
                    dedup_python_name = norm.py_name
                else:
                    h = hashlib.sha256()
                    h.update(f"{js_name}:{norm.py_name}:{i}".encode("utf-8"))
                    d = f"x{h.hexdigest()[0:8]}"
                    dedup_python_name = re.sub(
                        rf"^({settings.NPYM_PREFIX}\.)?(.*)$",
                        lambda m: f"{m.group(1)}{d}.{m.group(2)}",
                        norm.py_name,
                    )

                to_add_real.append(
                    dict(
                        js_name=js_name,
                        python_name=dedup_python_name,
                        python_name_base=searchable_py_name(python_name),
                        python_name_searchable=searchable_py_name(dedup_python_name),
                        dedup_seq=i,
                    )
                )

        Distribution.objects.bulk_insert(to_add_real)

    def import_names(self) -> None:
        """
        There are about 2 million packages in NPM and we need to normalize
        packages names in a conflict-prone way. Which means, we're forced to
        pre-import all packages name if we want to efficiently be able to index
        their names. This kinds of sucks but that's life I guess.

        Someone makes an export of these names and publishes it on GitHub
        every day, so we're using that list instead of doing god knows what
        in the CouchDB interface from NPM. In theory though we could receive
        names update in real-time but that'll be for much later.
        """

        with httpx.Client() as client, client.stream(
            "GET",
            self.NAMES_JSON,
            timeout=30,
        ) as response:
            data = json_stream.httpx.load(response)

            for chunk in ChunkIterator(data).chunks(10_000):
                to_add = []

                for name in chunk:
                    norm_name = self._make_norm_name(name)
                    to_add.append(dict(js_name=name, python_name=norm_name.py_name))

                self._insert_distributions(to_add)
