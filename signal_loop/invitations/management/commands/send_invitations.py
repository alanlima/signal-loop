import json

from django.core.management.base import BaseCommand

from signal_loop.invitations.services import send_window_invitations


class Command(BaseCommand):
    help = "Send opening invitations for one open window using trusted verified contacts."

    def add_arguments(self, parser):
        parser.add_argument("window", type=int)

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(send_window_invitations(window_id=options["window"]), sort_keys=True))
