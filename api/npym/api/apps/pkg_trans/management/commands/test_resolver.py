from django.core.management import BaseCommand
from rich.pretty import pprint

from npym.api.apps.pkg_trans.models import Version
from npym.api.apps.pkg_trans.resolver import Resolver


class Command(BaseCommand):
    def handle(self, *args, **options):
        v = Version.objects.get(distribution__js_name="express", js_version="4.18.2")
        # v = Version.objects.get(distribution__js_name='@vue/cli', js_version='5.0.8')
        # v = Version.objects.get(distribution__js_name='prettier', js_version='2.8.4')
        # v = Version.objects.get(distribution__js_name="mjml", js_version="4.13.0")
        # v = Version.objects.get(distribution__js_name="nuxt", js_version="3.2.3")
        # v = Version.objects.get(distribution__js_name="nuxt", js_version="3.3.0-27968571.4f61e36c6")
        # v = Version.objects.get(
        #     distribution__js_name="sass-loader", js_version="13.2.0"
        # )
        r = Resolver(v)
        r.build_dep_tree()

        pprint(r.root)
