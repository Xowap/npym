from django.core.management import BaseCommand
from rich.pretty import pprint

from npym.api.apps.pkg_trans.models import Distribution


class Command(BaseCommand):
    """
    Useful to remove artifacts that we don't want anymore (for development)
    """

    def handle(self, *args, **options):
        pprint(Distribution.objects.exclude(generated_for__isnull=True).delete())
        pprint(
            Distribution.objects.exclude(dependencies=False).update(dependencies=False)
        )
