from django.core.management import BaseCommand

from npym.apps.pkg_trans.models import Archive


class Command(BaseCommand):
    """
    Helps to free up cache from mistakes. Mostly intended for dev purposes.
    Freeing production archives can be implemented by checking the number of
    downloads of each archive over a time period and deleting the ones that
    are not used anymore for example.
    """

    def handle(self, *args, **options):
        for archive in Archive.objects.all():
            archive.archive.delete()
            archive.delete()
