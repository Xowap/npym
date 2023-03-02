from urllib.parse import quote
from uuid import uuid4

from django.db import models
from psqlextra.models import PostgresModel


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

    js_name = models.CharField(
        max_length=1000,
        help_text="The canonical NPM name of this package",
        unique=True,
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
        db_index=True,
    )
    dedup_seq = models.IntegerField(
        help_text=(
            "Helps to deduplicate JS names smashed into the same Python "
            "package with a stable order"
        )
    )
    description = models.TextField(blank=True, default="")

    @property
    def npm_url(self):
        return f"https://www.npmjs.com/package/{quote(self.js_name)}"

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
