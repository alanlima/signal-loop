import json

from django.core.management.base import BaseCommand

from signal_loop.pipeline.scheduling import dispatch_due


class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write(json.dumps(dispatch_due(), sort_keys=True))
