from django.core.management import BaseCommand

from npym.apps.pkg_trans.npm import Npm


class Command(BaseCommand):
    """
    It's quite the pain in the arsehole to look in real time for a NPM package
    so we'll load the whole list of packages and associated names in order to
    be able to look for said names when someone makes a request.

    The main difference between NPM and Python is that NPM won't auto-normalize
    package names while Python tools are encouraged to do so. Also, Python
    names are more strict than NPM names so an automatic mapping has to be
    done. As a result, it's impossible to guess the NPM package name from the
    Python package name if you didn't pre-map the whole thing.
    """

    def handle(self, *args, **options):
        npm = Npm()
        npm.import_names()
