import base64
import hashlib
import json
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence, Mapping, Callable, TypeVar, Generic, Tuple, MutableMapping

import httpx

from .models import Distribution, Version
from .version_man import sem_range_to_py_range


def file_digest(file, algorithm):
    """
    Computes the hash of a given file
    """

    h = hashlib.new(algorithm)

    while buf := file.read(4096):
        h.update(buf)

    return h


def sanitize(name: str) -> str:
    """
    Drop all new lines, non-printable characters, etc.
    """

    return re.sub(r"([^\x20-\x7e]|[\r\n])+", " ", f"{name}")


def urlsafe_b64encode_nopad(data):
    """
    From the Python docs, to help generating the RECORDS file
    """

    return base64.urlsafe_b64encode(data).rstrip(b"=")


T = TypeVar("T")


@dataclass(frozen=True)
class DedupMapEntry(Generic[T]):
    """
    Output of the dedup function below
    """

    original: str
    transformed: str
    value: T


def dedup_python_key(k: str, i: int) -> str:
    """
    Transforms a name into a Python module, used to generate entrypoints in a
    Python-compatible way through dedup_map() below.

    Parameters
    ----------
    k
        Key you want to deduplicate
    i
        Index of that key's occurrence
    """

    k = re.sub(r"[^a-z0-9]+", "_", k.lower()).strip('_')

    if i == 0:
        return k
    else:
        return f"{k}_{i}"


def dedup_map(data: Mapping[str, T], transform: Callable[[str, int], str]) -> Mapping[str, DedupMapEntry[T]]:
    """
    Uses the transform function to transform all keys in the mapping. If once
    transformed, two keys are identical, then we will append a number to the
    name. In order to figure duplicates, it will call transform(key, 0) and
    then if duplicate there is it will call transform(key, 1) and so on.

    Parameters
    ----------
    data
        The mapping to deduplicate
    transform
        The function to transform the keys
    """

    seen = set()
    result = {}

    for key, value in data.items():
        new_key = transform(key, 0)

        if new_key in seen:
            i = 1

            while new_key in seen:
                new_key = transform(key, i)
                i += 1

        seen.add(new_key)
        result[new_key] = DedupMapEntry(key, new_key, value)

    return result


class PackageTranslator:
    def __init__(self, distribution: Distribution, version: Version, version_info):
        """
        Here the version_info is the data straight out of the NPM API
        """

        self.distribution = distribution
        self.version_info = version_info
        self.version = version
        self._work_dir = None
        self.work_dir = None

    @property
    def source_path(self):
        """
        Where we download the source NPM package
        """

        return self.work_dir / "source.tgz"

    @property
    def source_dir(self):
        """
        Where we uncompress the NPM source package
        """

        return self.work_dir / "source"

    @property
    def wheel_dir(self):
        """
        Where we build the wheel's structure
        """

        return self.work_dir / "wheel"

    @property
    def npm_package_dir(self):
        """
        Where we're going to store the package inside the wheel
        """

        path = self.wheel_dir / "npym/node_modules" / self.distribution.js_name

        if not path.is_relative_to(self.wheel_dir):
            raise ValueError("Invalid path")

        return path

    @property
    def dist_info_dir(self):
        """
        The dist-info folder for the wheel
        """

        path = (
            self.wheel_dir
            / f"{self.distribution.python_name}-{self.version.python_version}.dist-info"
        )

        if not path.is_relative_to(self.wheel_dir):
            raise ValueError("Invalid path")

        return path

    @property
    def wheel_path(self):
        """
        The actual path the .whl file we're creating
        """

        path = (
            self.work_dir
            / f"{self.distribution.python_name}-{self.version.python_version}-py3-none-any.whl"
        )

        if not path.is_relative_to(self.work_dir):
            raise ValueError("Invalid path")

        return path

    @property
    def py_module_dir(self):
        """
        If the package has entrypoints, they need to be put in a module. This
        computes the location of this module.
        """

        py_module = re.sub("[^a-z0-9.]+", "_", self.distribution.python_name)
        py_module = py_module.replace(".", "/")

        return self.wheel_dir / py_module

    def _download_source(self):
        """
        Downloads the source NPM package
        """

        url = self.version_info["dist"]["tarball"]

        with self.source_path.open("wb") as f, httpx.Client() as client:
            with client.stream("GET", url) as stream:
                for data in stream.iter_bytes():
                    f.write(data)

    def _check_source_integrity(self):
        """
        Making sure that the hash checks out
        """

        algo, b64_hash = self.version_info["dist"]["integrity"].split("-", 1)

        with self.source_path.open("rb") as f:
            digest = file_digest(f, algo)

        expected_digest = base64.b64decode(b64_hash)

        if digest.digest() != expected_digest:
            raise ValueError("Source integrity check failed")

    def _extract_source(self):
        """
        The NPM source is a tarball. We'll extract it in work_dir / source.
        """

        self.source_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(self.source_path) as tar:
            tar.extractall(self.source_dir)

    def _copy_source(self):
        """
        We copy the source from "work_dir/source/package" to the wheel
        by putting everything in
        "work_dir/wheel/npym/node_modules/<package_name>".
        """

        self.npm_package_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            self.source_dir / "package", self.npm_package_dir, dirs_exist_ok=True
        )

    def _write_lines(self, path: Path, lines: Sequence[str]):
        """
        Convenience tool to build files
        """

        with path.open("w") as f:
            f.write("".join(f"{line}\n" for line in lines))

    def _write_dist_info_wheel(self):
        """
        Kinda static for now, let's see what happens
        """

        lines = [
            "Wheel-Version: 1.0",
            "Generator: npym v1",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
        ]

        self._write_lines(self.dist_info_dir / "WHEEL", lines)

    def _write_dist_info_license(self):
        """
        Trying to write a license if we've got one. The only thing is that NPM
        is just giving you the name of the license instead of the whole file.
        TBH it doesn't really matter because at this stage we're installing the
        software, not exposing metadata.
        """

        if lic := self.version_info.get("license"):
            lines = [f"License: {lic}"]
            self._write_lines(self.dist_info_dir / "LICENSE", lines)

    def _generate_dependencies_req(self):
        """
        For now we squash together the dependencies and peerDependencies. This
        most likely won't work for anything serious but implementing peer
        dependencies for Python package managers is going to be a fun ride.

        Of course, we resolve dependencies' names based on the mapping that
        we got. If we can't find a package well too bad.
        """

        base_dependencies = self.version_info.get("dependencies", {})
        peer_dependencies = self.version_info.get("peerDependencies", {})

        dependencies = {
            **base_dependencies,
            **peer_dependencies,
        }

        out = {"npym": ">=0.0.0"}
        name_map = {
            d.js_name: d.python_name
            for d in Distribution.objects.filter(js_name__in=dependencies)
        }

        for name, version in dependencies.items():
            if name in name_map:
                try:
                    out[name_map[name]] = sem_range_to_py_range(version)
                except ValueError:
                    out[name_map[name]] = ">=0.0.0"

        return out

    def _write_dist_info_metadata(self):
        """
        Tries to more or less convert the metadata from the NPM package into a
        Python package. Not a wonderful mapping but what matters most is that
        dependencies get listed correctly.
        """

        def get_author_info():
            a = self.version_info.get("author", {})

            if isinstance(a, str):
                return a, ""

            return a.get("name", ""), a.get("email", "")

        def get_bug_tracker():
            bugs = self.version_info.get("bugs", {})

            if isinstance(bugs, str):
                return bugs

            return bugs.get("url", "")

        homepage = self.version_info.get("homepage", "")
        repository = self.version_info.get("repository", {}).get("url", "")
        author, author_email = get_author_info()
        keywords = self.version_info.get("keywords", [])
        description = self.version_info.get("description", "")
        maintainers = self.version_info.get("maintainers", [])
        bugs_tracker = get_bug_tracker()
        version = self.version.python_version
        license_ = self.version_info.get("license", "")
        req = self._generate_dependencies_req()

        maintainers_names = [m["name"] for m in maintainers if m.get("name")]
        maintainers_emails = [m["email"] for m in maintainers if m.get("email")]

        lines = [
            f"Metadata-Version: 2.1",
            f"Name: {self.distribution.python_name}",
            f"Version: {version}",
            f"Summary: {sanitize(description)}",
        ]

        if homepage:
            lines.append(f"Home-page: {sanitize(homepage)}")

        if keywords:
            lines.append(f"Keywords: {','.join(sanitize(k) for k in keywords)}")

        if author:
            lines.append(f"Author: {sanitize(author)}")

        if author_email:
            lines.append(f"Author-email: {sanitize(author_email)}")

        if maintainers_names:
            lines.append(
                f"Maintainer: {', '.join(sanitize(m) for m in maintainers_names)}"
            )

        if maintainers_emails:
            lines.append(
                f"Maintainer-email: {', '.join(sanitize(m) for m in maintainers_emails)}"
            )

        if license_:
            lines.append(f"License: {sanitize(license_)}")

        if bugs_tracker:
            lines.append(f"Project-URL: Bug Tracker, {sanitize(bugs_tracker)}")

        if repository:
            lines.append(f"Project-URL: Repository, {sanitize(repository)}")

        if req:
            for package, version in req.items():
                lines.append(f"Requires-Dist: {package} ({version})")

        self._write_lines(self.dist_info_dir / "METADATA", lines)

    def _write_dist_info_records(self):
        """
        Basically we compute the hash of every single file in the archive and
        write it down this RECORDS file.
        """

        lines = []

        for path in self.wheel_dir.glob("**/*"):
            if path.is_file():
                rel_path = path.relative_to(self.wheel_dir)
                with path.open("rb") as f:
                    h = f"sha256={urlsafe_b64encode_nopad(file_digest(f, 'sha256').digest()).decode('ascii')}"
                s = path.stat().st_size

                lines.append(f"{rel_path},{h},{s}")

        lines.append(f"{self.dist_info_dir.relative_to(self.wheel_dir)}/RECORD,,")

        self._write_lines(self.dist_info_dir / "RECORD", lines)

    def _guess_entry_points(self) -> Tuple[Mapping[str, DedupMapEntry], Mapping[str, str]]:
        """
        Parsing the bin argument from package.json in order to deduce the
        expected entry points and their naming in Python.
        """

        scripts = self.version_info.get('bin', {})

        if isinstance(scripts, str):
            scripts = {Path(self.distribution.js_name).name: scripts}
        else:
            scripts = {Path(k).name: v for k, v in scripts.items()}

        scripts = dedup_map(scripts, dedup_python_key)
        entrypoints: MutableMapping[str, str] = {}

        for entry in scripts.values():
            entrypoints[entry.transformed] = entry.value

        return scripts, entrypoints

    def _write_module_init(self, entrypoints: Mapping[str, str]):
        """
        We leverage npym's EntryPoints facility to minimize the amount of code
        we need to generate here.

        Parameters
        ----------
        entrypoints
            The generated list of entrypoints
        """

        if not entrypoints:
            return

        kwargs = dict(
            package=self.distribution.js_name,
            scripts=entrypoints,
        )

        lines = [
            "from npym import EntryPoints",
            f"entrypoints = EntryPoints.from_json({json.dumps(kwargs)!r})"
        ]

        self._write_lines(self.py_module_dir / "__init__.py", lines)

    def _write_module_main(self, entrypoints: Mapping[str, str]):
        """
        If there is one entrypoint, we'll allow it to be ran as a Python module
        (for example "python -m npym.prettier"). This requires a __main__.py
        file that we're creating here.

        Parameters
        ----------
        entrypoints
            Deduced entrypoints
        """

        if len(entrypoints) != 1:
            return

        lines = [
            f"from {self.distribution.python_name} import entrypoints",
            f"entrypoints.{[*entrypoints][0]}()",
        ]

        self._write_lines(self.py_module_dir / "__main__.py", lines)

    def _write_entrypoints_txt(self, scripts: Mapping[str, DedupMapEntry]):
        """
        entry_points.txt indicates to the package manager which bins needs to
        be created when the package is installed. That's where we do the
        mapping between the name of the script as asked by JS and the name of
        the Python function to call (which we generated earlier).

        Parameters
        ----------
        scripts
            Entrypoints map, generated a few steps before
        """

        if not scripts:
            return

        lines = ["[console_scripts]"]

        for entry in scripts.values():
            lines.append(f"{entry.original}={self.distribution.python_name}:entrypoints.{entry.transformed}")

        self._write_lines(self.dist_info_dir / "entry_points.txt", lines)

    def _write_bin(self):
        """
        Umbrella call for all which pertains to bin and entrypoints
        """

        self.py_module_dir.mkdir(parents=True, exist_ok=True)
        scripts, entrypoints = self._guess_entry_points()
        self._write_module_init(entrypoints)
        self._write_module_main(entrypoints)
        self._write_entrypoints_txt(scripts)

    def _write_dist_info(self):
        """
        Umbrella to call all the functions that will build the various files
        inside the dist-info folder.
        """

        self.dist_info_dir.mkdir(parents=True, exist_ok=True)
        self._write_dist_info_wheel()
        self._write_dist_info_license()
        self._write_dist_info_metadata()
        self._write_dist_info_records()
        self._write_bin()

    def _zip_wheel(self):
        """
        All the content of the wheel has been laid out in the working folder,
        now we generate a full zip file containing all this.
        """

        with self.wheel_path.open("wb") as f:
            with zipfile.ZipFile(
                f, "w", compresslevel=9, compression=zipfile.ZIP_DEFLATED
            ) as z:
                for path in self.wheel_dir.glob("**/*"):
                    if path.is_file():
                        z.write(path, path.relative_to(self.wheel_dir))

    def _translate(self):
        """
        Umbrella function to call all the steps of the process one by one
        """

        self._download_source()
        self._check_source_integrity()
        self._extract_source()
        self._copy_source()
        self._write_dist_info()
        self._zip_wheel()

    def __enter__(self):
        """
        We're a context manager, this way we can return the name of the
        generated wheel, let the caller handle it and then delete the file
        when we exit.
        """

        self._work_dir = TemporaryDirectory()
        self.work_dir = Path(self._work_dir.name)
        self._translate()

        return self.wheel_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Everything must go away now.
        """

        self._work_dir.cleanup()
