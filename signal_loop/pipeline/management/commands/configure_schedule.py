from django.core.management.base import BaseCommand, CommandError

from signal_loop.pipeline.scheduling import configure_schedule


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("organisation", type=int)
        parser.add_argument("timezone")

    def handle(self, *args, **options):
        try:
            configure_schedule(organisation_id=options["organisation"], timezone_name=options["timezone"])
        except Exception:
            raise CommandError("invalid_schedule") from None
        self.stdout.write("schedule_configured")
