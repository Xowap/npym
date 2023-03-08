from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from django.db import models
from django.utils.functional import cached_property
from packaging.version import Version as PyVersion
from psqlextra.models import PostgresModel


def return_false():
    """
    Stupid callable so that JSONField doesn't emmit a warning about the default
    parameter not being a callable.
    """

    return False


class UuidPkModel(PostgresModel):
    """
    Mixin to make a model having a UUID field as primary key (useful to avoid
    sequential IDs when you want to be a bit discreet about how many clients
    you got or if you want to avoid predictable IDs for security reasons).
    """

    class Meta:
        abstract = True

    id = models.UUIDField(
        primary_key=True,
        editable=False,
        default=uuid4,
    )


class Distribution(UuidPkModel):
    """
    We just acknowledge here the existence of this given JS package and its
    mapping to a Python distribution.
    """

    class Meta:
        unique_together = [
            ("generated_for", "js_name"),
        ]

    js_name = models.CharField(
        max_length=1000,
        help_text="The canonical NPM name of this package",
    )
    python_name = models.CharField(
        max_length=1000,
        help_text="The normalized Python name of this distribution",
        unique=True,
    )
    python_name_base = models.CharField(
        max_length=1000,
        help_text="The normalized Python name of this distribution, without dedup",
        db_index=True,
    )
    python_name_searchable = models.CharField(
        max_length=1000,
        help_text="The normalized Python name of this distribution, with dots replaced by dashes, so that the name is searchable",
        unique=True,
    )
    dedup_seq = models.IntegerField(
        help_text=(
            "Helps to deduplicate JS names smashed into the same Python "
            "package with a stable order"
        )
    )
    description = models.TextField(blank=True, default="")
    original = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="copies",
        null=True,
        help_text=(
            "Copies are made in order to help with resolving conflicting "
            "versions, since Python package managers don't deal with nested "
            "versions like NPM."
        ),
    )
    generated_for = models.ForeignKey(
        "Version",
        on_delete=models.CASCADE,
        related_name="subtree",
        null=True,
        help_text=(
            "Non-NULL values indicate that this distribution was generated for"
            " a particular version of the package. We need to know that in "
            "order to check the signature."
        ),
    )
    dependencies = models.JSONField(
        default=return_false,
        blank=True,
        help_text=(
            "Pre-resolved dependencies of this package. False if the "
            "resolution did not happen yet (meaning it needs to be done "
            "before serving the package). Will be defined for tree leaves."
        ),
    )

    def __str__(self):
        return self.python_name

    @property
    def npm_url(self):
        return f"https://www.npmjs.com/package/{quote(self.js_name)}"

    @property
    def real(self):
        """
        Because some distributions are auto-generated sub-tree nodes, we need
        a simple way to obtain the real distribution behind that one for some
        metadata when generating the package.
        """

        return self.original or self

    def wheel_name(
        self,
        version: str,
        python_tag: str = "py3",
        abi_tag: str = "none",
        platform_tag: str = "any",
    ) -> str:
        name = self.python_name.replace("-", "_").replace(".", "_")
        return f"{name}-{version}-{python_tag}-{abi_tag}-{platform_tag}.whl"


class Version(UuidPkModel):
    """
    A version of a given distribution. We don't care so much about parsing the
    version number here, we just keep it as-is hoping that the package manager
    will pick up.
    """

    class Meta:
        unique_together = ("distribution", "python_version")

    distribution = models.ForeignKey(
        Distribution,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    python_version = models.CharField(max_length=100)
    js_version = models.CharField(max_length=100)
    dependencies = models.JSONField(
        default=return_false,
        blank=True,
        help_text=(
            "Pre-resolved dependencies of this package. False if the "
            "resolution did not happen yet (meaning it needs to be done "
            "before serving the package). Will be defined for tree roots."
        ),
    )

    def __str__(self):
        return f"{self.distribution}@{self.js_version}"

    @cached_property
    def parsed_py_version(self) -> PyVersion:
        """
        That's useful for things like sorting
        """

        return PyVersion(self.python_version)


def upload_to_archive(instance: "Archive", _: str) -> str:
    """
    We must generate a file name that is matching the name of the Python wheel,
    which is
    {distribution}-{version}(-{build tag})?-{python tag}-{abi tag}-{platform tag}.whl

    - Distribution = distribution name
    - Version = version name
    - Build tag = we don't have any, we're just reflecting NPM versions
    - Python tag = we'll say that we're compatible with py3
    - ABI tag = we'll say that we're compatible with any ABI
    - Platform tag = we'll say that we're compatible with any platform
    """

    translator = instance.translator
    version = instance.version.python_version
    wheel_name = instance.version.distribution.wheel_name(version)

    b1 = instance.hash_sha256[0:2]
    b2 = instance.hash_sha256[2:4]
    b3 = instance.hash_sha256[4:6]
    b4 = instance.hash_sha256[6:8]

    return f"distributions/{translator}/{b1}/{b2}/{b3}/{b4}/{wheel_name}"


class Archive(UuidPkModel):
    """
    A distribution archive for a specific version of a distribution. We leave
    the possibility to have wheels and sdists, but we only support wheels for
    now.

    The translator version is used so we are able to change the way we
    translate packages in the future, which would trigger a re-generation of
    packages without having to override the old file.
    """

    class Meta:
        unique_together = [
            ("version", "format", "translator"),
        ]

    class Format(models.TextChoices):
        wheel = "wheel"
        sdist = "sdist"

    class Translator(models.TextChoices):
        v1 = "v1"

    version = models.ForeignKey(
        Version,
        on_delete=models.CASCADE,
        related_name="archives",
    )
    format = models.CharField(
        max_length=max(len(x[0]) for x in Format.choices),
        choices=Format.choices,
    )
    translator = models.CharField(
        max_length=max(len(x[0]) for x in Translator.choices),
        choices=Translator.choices,
    )
    hash_sha256 = models.CharField(max_length=64)
    archive = models.FileField(upload_to=upload_to_archive)

    def __str__(self):
        return f"{Path(self.archive.path).name}"


class Download(PostgresModel):
    """
    For the sake of statistics, we keep track of the downloads (anonymously).
    This might serve in the future for cache-busting purposes or other
    cost-killing measure (also for vanity metrics).
    """

    archive = models.ForeignKey(
        Archive,
        on_delete=models.CASCADE,
        related_name="downloads",
    )
    date = models.DateTimeField(auto_now_add=True)
