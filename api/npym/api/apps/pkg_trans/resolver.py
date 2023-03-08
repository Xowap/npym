import asyncio
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import product
from typing import (
    Any,
    Mapping,
    MutableMapping,
    MutableSequence,
    Optional,
    Sequence,
    Tuple,
)

import httpx
import lark
from django.urls import reverse
from packaging.version import Version as PyVersion
from psqlextra.types import ConflictAction
from semver import VersionInfo as SemVersion
from wheel_filename import parse_wheel_filename

from .models import Archive, Distribution, Version
from .npm import Npm, PackageInfo, searchable_py_name, version_sem_to_py
from .version_man import (
    Range,
    flatten_py_range,
    intersect_ranges,
    parse_spec,
    union_ranges,
)


@dataclass
class VersionInfo:
    """
    Display information for a version
    """

    url: str
    file_name: str
    hash: str


class VersionConstraint:
    """
    When we're building the dependency tree, we need to know if successive
    version specifications are compatible with one another. This helps keeping
    track of the intersection of version specs and to know when it's not
    intersecting (meaning when we need to create a branch in the tree).
    """

    def __init__(self, ranges: Sequence[Range]):
        self.ranges = ranges

    @classmethod
    def from_spec(cls, spec: str) -> "VersionConstraint":
        """
        Generates initial constraint from string out of package.json

        Parameters
        ----------
        spec
            String from package.json
        """

        return cls(parse_spec(spec))

    @property
    def has_matches(self):
        """
        Indicates if this constraint is still matching anything
        """

        return len(self.ranges) > 0

    def __repr__(self):
        return f"{self.__class__.__name__}({self.ranges!r})"

    def accept(self, version: str) -> bool:
        """
        Checks if a given version from a package is accepted.

        Parameters
        ----------
        version
            Version that we want to test
        """

        version = SemVersion.parse(version)

        for r in self.ranges:
            if r.contains(version):
                return True

        return False

    def intersect(self, other: "VersionConstraint") -> "VersionConstraint":
        """
        Generates a new constraint that is the intersection of the current
        one and the other one. Current constraint isn't modified.

        Parameters
        ----------
        other
            Other version constraint to intersect
        """

        out = []

        for a, b in product(self.ranges, other.ranges):
            out.extend(intersect_ranges([a, b]))

        return VersionConstraint(union_ranges(out))

    def flat_py_range(self) -> str:
        """
        Converts into a Python range
        """

        return flatten_py_range(
            f"{self!r}",
            [r.as_py_range() for r in self.ranges],
        )


def _package_versions(
    distribution: Distribution, package_info: PackageInfo
) -> Mapping[Version, Mapping]:
    """
    Internal backend for both package_versions() and Resolver(). It will
    generate a mapping between the versions from NPM and our local Version
    object.

    Parameters
    ----------
    distribution
        Distribution object for which we want to get the versions
    package_info
        Package info as returned by NPM
    """

    out = {}

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

    for version in sorted(
        distribution.versions.all(),
        key=lambda v: PyVersion(v.python_version),
        reverse=True,
    ):
        out[version] = package_info["versions"][version.js_version]

    return out


def package_versions(
    distribution: Distribution,
    package_info: PackageInfo,
    signature: str = "",
) -> Sequence[VersionInfo]:
    """
    As the version mapping between NPM and Python is not guaranteed to be 1:1,
    we need to keep track of what mapping we do so that we don't map two
    different NPM versions to the same Python version.

    This fetches the versions from NPM, looks for archives for each of them,
    stores the new versions found in NPM, computes what has to be displayed,
    etc.
    """

    info = _package_versions(distribution, package_info)

    versions = {}
    out = []

    for arch in Archive.objects.filter(
        version__distribution__js_name=package_info["name"],
        version__distribution__generated_for=None,
        format=Archive.Format.wheel,
        translator=Archive.Translator.v1,
    ):
        versions[arch.version.python_version] = arch

    for version_obj, version_info in info.items():
        version = version_obj.python_version

        if version in versions:
            hash_ = versions[version].hash_sha256
        else:
            hash_ = ""

        if signature:
            computed_signature = hash_data(
                dict(
                    name=version_obj.distribution.generated_for.distribution.js_name,
                    version=version_obj.distribution.generated_for.js_version,
                    path=distribution.js_name,
                    dependencies=version_info.get("dependencies", {}),
                )
            )

            if f"x{computed_signature}" != signature:
                continue

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


def hash_data(data: Any, out_length: int = 8) -> str:
    """
    Given a JSON-serializable object, return a SHA-256 hash of it (after
    normalizing it so that it stays stable).

    Parameters
    ----------
    data
        JSON-serializable object to hash
    out_length
        Max length of the expected output
    """

    as_str = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(as_str.encode("utf-8")).hexdigest()[:out_length]


@dataclass
class ResolvedDependency:
    """
    Intermediate representation right after we've parsed the dependencies
    from package.json
    """

    version: Version
    constraint: VersionConstraint


@dataclass(frozen=True)
class DeepFetchQuery:
    """
    Used internally by deep_fetch() to know which package to query from NPM
    """

    js_name: str
    spec: str


@dataclass
class NodeResolution:
    """
    When we're making the tree, this is the part of the meta-data that is
    inferred from the tree for each node and that allows to generate the whole
    thing.
    """

    python_name: str
    js_name: str


@dataclass
class Node:
    """
    A node of the tree. The idea with this tree is to mimic what NPM is doing,
    with a little twist.

    NPM would install the dependency you're asking for and its dependencies at
    the same level if possible. Here, since we don't know what other
    dependencies will be installed, we can't think like that. So the package
    that we're analyzing right now becomes the root and all other dependencies
    go under it in the tree.

    Other than that, we keep the tree as flat as possible, just making branches
    when there is a version conflict.
    """

    version: Optional[Version]
    parent: Optional["Node"]
    children: MutableSequence["Node"]
    constraint: Optional[VersionConstraint]
    resolution: Optional[NodeResolution] = None
    _dist_cache: MutableMapping[Distribution, "Node"] = field(
        default_factory=dict, repr=False
    )

    @property
    def root(self) -> "Node":
        """
        Finds the root of the tree
        """

        ptr = self

        while ptr.parent is not None:
            ptr = ptr.parent

        return ptr

    @property
    def ancestors_js_names(self) -> Sequence[str]:
        """
        Generates the succession of JS names that you need to figure the path
        of that module on disk.
        """

        names = [self.version.distribution.js_name]
        ptr = self

        while ptr.parent is not None:
            ptr = ptr.parent
            names.append(ptr.version.distribution.js_name)

        return names[::-1]

    def add_child(self, version: Version, constraint: VersionConstraint) -> "Node":
        """
        Add a child to the current node.
        """

        node = Node(
            version=version,
            parent=self,
            children=[],
            constraint=constraint,
        )
        self.children.append(node)
        self._dist_cache[version.distribution] = node

        return node

    def node_for(self, distribution: Distribution) -> Optional["Node"]:
        """
        Tries to find if this node is already present here or above, used to
        know if there is a version conflict or not.

        Parameters
        ----------
        distribution
            Distribution that you're looking for
        """

        if distribution in self._dist_cache:
            return self._dist_cache[distribution]

        if self.parent is None:
            return None
        else:
            return self.parent.node_for(distribution)

    def ingest(
        self, resolver: "Resolver", current_node: "Node", dep: ResolvedDependency
    ) -> Tuple[bool, "Node"]:
        """
        We're going to add a dependency to the tree. The goal is to put this
        node as high as possible in the tree, as long as we don't introduce
        an impossible constraint.

        We need to take the following decision:

        - Stick this dependency up top if not specified yet
        - If specified
            - Find the spec node and modify it if it intersects
            - Add the dependency as a child of current node

        Parameters
        ----------
        resolver
            The Resolver instance which we need in order to access the NPM API
            and specifically to be sure to go through the cache that we have.
        dep
            Dependency to add to the tree
        current_node
            The node currently requesting this dependency
        """

        node = self.node_for(dep.version.distribution)

        if node is not None:
            common = node.constraint.intersect(dep.constraint)
            best_version = None

            if common.has_matches:
                best_version = resolver.find_best_version(
                    common, dep.version.distribution
                )

            if common.has_matches and best_version is not None:
                node.constraint = common
                old_version = node.version
                node.version = best_version
                return old_version != best_version, node
            else:
                return True, current_node.add_child(
                    version=dep.version,
                    constraint=dep.constraint,
                )
        else:
            return True, self.root.add_child(
                version=dep.version,
                constraint=dep.constraint,
            )


class Resolver:
    """
    When you install dependencies using NPM, it will resolve "version
    conflicts" by giving sub-dependencies their own custom node_modules dir
    with their own dependencies. The issue is that in Python there is a single
    "environment" shared regardless of the current package.

    Said in other words, if you do a "require" in node, it will start to
    import modules in the current module's node_modules, then in the parent's
    and so forth. If you "import" in Python it wills imply look into the
    current path and return the first module it finds, regardless of where you
    import from.

    Since Node developers fully take advantage of this feature of NPM in order
    to completely chicken out and break APIs every 6 months, no serious Node
    package can be installed without implementing this feature to some extent.
    The only issue being that Python package managers don't give a fuck.

    So what we're doing is that we're pre-resolving dependencies of root
    packages we generate on-the-fly "nested" version of packages that will
    allow to resolve dependencies. While this is not optimal (we're resolving
    the tree at a given time, if a new version of a dependency is released
    we might "hide" it this way) but at least it'll offer a way to install
    dependencies that actually is possible.
    """

    def __init__(self, version: Version):
        self.version = version
        self.root = Node(
            version=version,
            constraint=VersionConstraint.from_spec(version.js_version),
            parent=None,
            children=[],
        )
        self._info_cache = {}
        self._version_cache = {}

    async def deep_fetch(self, query: DeepFetchQuery) -> None:
        """
        Fetching all package info for all dependencies one by one is extremely
        time-consuming. The goal of this method is to pre-fetch everything at
        once completely in parallel using asyncio. It's not guaranteed that it
        will select exactly the same packages as the resolver will do later on
        but it should at least fetch 95%+ of them. This speeds up the process
        a lot later on.

        This works because we have a _info_cache property which contains a
        cache of the package info.

        Parameters
        ----------
        query
            The initial package from which we're digging.
        """

        npm = Npm.instance()
        npm.renew_async_client()

        loop = asyncio.get_running_loop()
        to_fetch = {query}
        fetching = set()
        tasks = []
        locks = defaultdict(asyncio.Lock)

        async def fetch_one(q: DeepFetchQuery):
            try:
                async with locks[q.js_name]:
                    if q.js_name in self._info_cache:
                        info = self._info_cache[q.js_name]
                    else:
                        info = await npm.async_get_package_info(q.js_name)

                    constraint = VersionConstraint.from_spec(q.spec)
                    self._info_cache[q.js_name] = info

                    for version in sorted(
                        info.get("versions", {}).values(),
                        key=lambda v: SemVersion.parse(v["version"]),
                        reverse=True,
                    ):
                        if not constraint.accept(version["version"]):
                            continue

                        for package, spec in version.get("dependencies", {}).items():
                            to_fetch.add(DeepFetchQuery(js_name=package, spec=spec))

                        break
            except (httpx.HTTPError, lark.exceptions.LarkError, ValueError):
                pass

        async def fetch_diff():
            for n in to_fetch - fetching:
                tasks.append(loop.create_task(fetch_one(n)))
                fetching.add(n)

            await asyncio.gather(*tasks)
            tasks.clear()

        while to_fetch - fetching:
            await fetch_diff()

    def get_package_info(self, js_name: str) -> PackageInfo:
        """
        Returns the information from NPM about a package. We'll cache this in
        case we're called in the future. The cache is pre-warmed by
        deep_fetch() before doing anything.

        Parameters
        ----------
        js_name
            Name of the package.
        """

        if js_name not in self._info_cache:
            npm = Npm.instance()
            self._info_cache[js_name] = npm.get_package_info(js_name)

        return self._info_cache[js_name]

    def get_package_versions(
        self, distribution: Distribution, package_info: PackageInfo
    ) -> Mapping[Version, Mapping]:
        """
        Maps the NPM versions to actual versions from our DB (and creates them
        if needed).

        Parameters
        ----------
        distribution
            Distribution for which we want the versions
        package_info
            Data that we've got from NPM
        """

        if distribution.real.js_name not in self._version_cache:
            self._version_cache[distribution.js_name] = _package_versions(
                distribution, package_info
            )

        return self._version_cache[distribution.js_name]

    def find_best_version(
        self, constraint: VersionConstraint, distribution: Distribution
    ) -> Optional[Version]:
        """
        Looks for the highest version accepted by the constraint. We'll use
        this version to compute the tree.

        It's expected that similar versions will have similar dependencies,
        which means that even if we're computing the tree with this version
        (and preventing the installation of any other tree) the Python package
        manager should still have some latitude to upgrade above this version.

        Parameters
        ----------
        constraint
            Constraint that we're testing
        distribution
            Distribution for which we're looking for a version
        """

        package_info = self.get_package_info(distribution.real.js_name)

        for version in self.get_package_versions(distribution, package_info):
            if constraint.accept(version.js_version):
                return version

    def get_dependencies(self, version: Version) -> Sequence[ResolvedDependency]:
        """
        We'll extract from here the dependencies found in the package.json and
        parse it into a ResolvedDependency.

        Parameters
        ----------
        version
            Version to parse
        """

        package_info = self.get_package_info(version.distribution.js_name)
        version_info = self.get_package_versions(version.distribution, package_info)[
            version
        ]

        out = []

        for package, spec in version_info.get("dependencies", {}).items():
            distribution = Distribution.objects.get(js_name=package, generated_for=None)
            constraint = VersionConstraint.from_spec(spec)
            best_version = self.find_best_version(constraint, distribution)

            if not best_version:
                raise ValueError(
                    f"Could not find a version for {distribution} that satisfies {spec}"
                )

            out.append(ResolvedDependency(version=best_version, constraint=constraint))

        return out

    def build_dep_tree(self):
        """
        Build a dependency tree for the given version.
        """

        asyncio.run(
            self.deep_fetch(
                DeepFetchQuery(
                    self.root.version.distribution.js_name,
                    self.root.version.js_version,
                )
            ),
        )
        queue = [self.root]

        while queue and (node := queue.pop(0)):
            for dep in self.get_dependencies(node.version):
                modified, new_node = node.ingest(self, node, dep)

                if modified:
                    queue.append(new_node)

    def save_dependencies(self):
        """
        Saves the dependencies tree into DB so that the package can be
        installed.
        """

        self._resolve_nodes()
        self._create_distributions()

    def _create_distributions(self):
        """
        Creates all the virtual distributions that we're going to need for
        installing this tree.
        """

        queue = [self.root]
        to_create = []

        while queue and (node := queue.pop(0)):
            dependencies = {}

            for child in node.children:
                dependencies[
                    child.resolution.python_name
                ] = child.constraint.flat_py_range()
                queue.append(child)

            searchable_name = searchable_py_name(node.resolution.python_name)

            if node is self.root:
                self.root.version.dependencies = dependencies
                self.root.version.save(update_fields=["dependencies"])
            else:
                to_create.append(
                    Distribution(
                        original=node.version.distribution,
                        generated_for=self.root.version,
                        js_name=node.resolution.js_name,
                        python_name=node.resolution.python_name,
                        python_name_base=searchable_name,
                        python_name_searchable=searchable_name,
                        dedup_seq=0,
                        dependencies=dependencies,
                    )
                )

        Distribution.objects.bulk_create(to_create)

    def _resolve_nodes(self):
        """
        Resolves the path of JS modules on-disk before we can generate the
        whole tree.
        """

        queue = [self.root]

        while queue and (node := queue.pop(0)):
            package_info = self.get_package_info(node.version.distribution.js_name)
            version_info = self.get_package_versions(
                node.version.distribution, package_info
            )[node.version]
            js_name = "/node_modules/".join(node.ancestors_js_names)
            signature_data = {
                "name": self.root.version.distribution.js_name,
                "version": self.root.version.js_version,
                "path": js_name,
                "dependencies": version_info.get("dependencies", {}),
            }

            node.resolution = NodeResolution(
                python_name=f"{node.version.distribution.python_name}.x{hash_data(signature_data)}",
                js_name=js_name,
            )

            queue.extend(node.children)

    def resolve(self):
        """
        Call this to resolve dependencies. After that your root package will
        have all its properties set correctly.
        """

        self.build_dep_tree()
        self.save_dependencies()
