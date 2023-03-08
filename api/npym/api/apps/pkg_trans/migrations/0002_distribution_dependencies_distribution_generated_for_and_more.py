# Generated by Django 4.1.7 on 2023-03-07 20:34

from django.db import migrations, models
import django.db.models.deletion
import npym.api.apps.pkg_trans.models


class Migration(migrations.Migration):
    dependencies = [
        ("pkg_trans", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="distribution",
            name="dependencies",
            field=models.JSONField(
                blank=True,
                default=npym.api.apps.pkg_trans.models.return_false,
                help_text="Pre-resolved dependencies of this package. False if the resolution did not happen yet (meaning it needs to be done before serving the package). Will be defined for tree leaves.",
            ),
        ),
        migrations.AddField(
            model_name="distribution",
            name="generated_for",
            field=models.ForeignKey(
                help_text="Non-NULL values indicate that this distribution was generated for a particular version of the package. We need to know that in order to check the signature.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subtree",
                to="pkg_trans.version",
            ),
        ),
        migrations.AddField(
            model_name="distribution",
            name="original",
            field=models.ForeignKey(
                help_text="Copies are made in order to help with resolving conflicting versions, since Python package managers don't deal with nested versions like NPM.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="copies",
                to="pkg_trans.distribution",
            ),
        ),
        migrations.AddField(
            model_name="version",
            name="dependencies",
            field=models.JSONField(
                blank=True,
                default=npym.api.apps.pkg_trans.models.return_false,
                help_text="Pre-resolved dependencies of this package. False if the resolution did not happen yet (meaning it needs to be done before serving the package). Will be defined for tree roots.",
            ),
        ),
        migrations.AlterField(
            model_name="distribution",
            name="python_name_searchable",
            field=models.CharField(
                help_text="The normalized Python name of this distribution, with dots replaced by dashes, so that the name is searchable",
                max_length=1000,
                unique=True,
            ),
        ),
    ]
