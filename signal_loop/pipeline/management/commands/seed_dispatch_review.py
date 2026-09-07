from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from signal_loop.membership.models import Organisation, Project
from signal_loop.pipeline.models import WindowDispatch
from signal_loop.pipeline.scheduling import configure_schedule
from signal_loop.windows.models import WeeklyWindow
from signal_loop.windows.services import create_weekly_window


class Command(BaseCommand):
    help = "Explicit synthetic prior-window fixture for live beat/worker review."

    def handle(self, *args, **options):
        if not getattr(settings, "INVITATION_REVIEW_MODE", False):
            raise CommandError("synthetic_review_settings_required")
        call_command("seed_invitation_review", stdout=self.stdout)
        org = Organisation.objects.get(name="Synthetic invitation review")
        configure_schedule(organisation_id=org.pk, timezone_name="UTC")
        day = timezone.now().date()
        previous = day - timedelta(days=day.weekday() + 7)
        window = WeeklyWindow.objects.filter(organisation=org, week_start=previous).first()
        if window is None:
            # Explicit historical TEST FIXTURE, never called by production dispatcher.
            window = create_weekly_window(organisation=org, week_start=previous, timezone_name="UTC")
        WindowDispatch.objects.get_or_create(window=window, defaults={
            "projects": list(Project.objects.filter(organisation=org).values_list("pk", flat=True))})
        self.stdout.write("synthetic_dispatch_ready")
