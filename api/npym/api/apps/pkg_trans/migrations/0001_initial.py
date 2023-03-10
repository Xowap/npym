# Generated by Django 4.1.7 on 2023-02-28 15:39

from django.db import migrations, models
import django.db.models.deletion
import npym.api.apps.pkg_trans.models
import psqlextra.manager.manager
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Archive",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "format",
                    models.CharField(
                        choices=[("wheel", "Wheel"), ("sdist", "Sdist")], max_length=5
                    ),
                ),
                ("translator", models.CharField(choices=[("v1", "V1")], max_length=2)),
                ("hash_sha256", models.CharField(max_length=64)),
                (
                    "archive",
                    models.FileField(
                        upload_to=npym.api.apps.pkg_trans.models.upload_to_archive
                    ),
                ),
            ],
            managers=[
                ("objects", psqlextra.manager.manager.PostgresManager()),
            ],
        ),
        migrations.CreateModel(
            name="Distribution",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "js_name",
                    models.CharField(
                        help_text="The canonical NPM name of this package",
                        max_length=1000,
                        unique=True,
                    ),
                ),
                (
                    "python_name",
                    models.CharField(
                        help_text="The normalized Python name of this distribution",
                        max_length=1000,
                        unique=True,
                    ),
                ),
                (
                    "python_name_base",
                    models.CharField(
                        db_index=True,
                        help_text="The normalized Python name of this distribution, without dedup",
                        max_length=1000,
                    ),
                ),
                (
                    "python_name_searchable",
                    models.CharField(
                        db_index=True,
                        help_text="The normalized Python name of this distribution, with dots replaced by dashes, so that the name is searchable",
                        max_length=1000,
                    ),
                ),
                (
                    "dedup_seq",
                    models.IntegerField(
                        help_text="Helps to deduplicate JS names smashed into the same Python package with a stable order"
                    ),
                ),
                ("description", models.TextField(blank=True, default="")),
            ],
            options={
                "abstract": False,
            },
            managers=[
                ("objects", psqlextra.manager.manager.PostgresManager()),
            ],
        ),
        migrations.CreateModel(
            name="Version",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("python_version", models.CharField(max_length=100)),
                ("js_version", models.CharField(max_length=100)),
                (
                    "distribution",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="pkg_trans.distribution",
                    ),
                ),
            ],
            options={
                "unique_together": {("distribution", "python_version")},
            },
            managers=[
                ("objects", psqlextra.manager.manager.PostgresManager()),
            ],
        ),
        migrations.CreateModel(
            name="Download",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateTimeField(auto_now_add=True)),
                (
                    "archive",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="downloads",
                        to="pkg_trans.archive",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "base_manager_name": "objects",
            },
            managers=[
                ("objects", psqlextra.manager.manager.PostgresManager()),
            ],
        ),
        migrations.AddField(
            model_name="archive",
            name="version",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="archives",
                to="pkg_trans.version",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="archive",
            unique_together={("version", "format", "translator")},
        ),
    ]
