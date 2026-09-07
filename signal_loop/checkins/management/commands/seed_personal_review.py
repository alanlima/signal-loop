from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership
from signal_loop.windows.services import create_weekly_window
from signal_loop.windows.models import WeeklyWindow


class Command(BaseCommand):
    help = "Create explicit synthetic personal-form fixtures; requires settings_personal_review."

    def handle(self, *args, **options):
        if not getattr(settings, "CHECKIN_REVIEW_MODE", False):
            raise CommandError("Use the explicit local synthetic review settings.")
        user, _ = get_user_model().objects.get_or_create(username="synthetic_personal_review")
        user.set_password("synthetic-review-password")
        user.save()
        for label, zone in (("Cedar", "Australia/Brisbane"), ("Birch", "America/New_York")):
            org, _ = Organisation.objects.get_or_create(name=f"Synthetic personal review {label}")
            project, _ = Project.objects.get_or_create(organisation=org, name=label)
            member, _ = OrganisationMembership.objects.get_or_create(organisation=org, user=user)
            ProjectMembership.objects.get_or_create(project=project, organisation_membership=member)
            local_day = timezone.now().astimezone(ZoneInfo(zone)).date()
            week = local_day - timedelta(days=local_day.weekday())
            if not WeeklyWindow.objects.filter(organisation=org, week_start=week).exists():
                create_weekly_window(organisation=org, week_start=week, timezone_name=zone)
        self.stdout.write("Synthetic review ready: synthetic_personal_review / synthetic-review-password")
        for label, count in (("ordinary", 1), ("many", 4), ("zero", 0)):
            name = f"synthetic_journey_{label}"
            fixture, _ = get_user_model().objects.get_or_create(username=name)
            fixture.set_password("synthetic-review-password")
            fixture.save()
            org, _ = Organisation.objects.get_or_create(name=f"Synthetic journey {label}")
            member, _ = OrganisationMembership.objects.get_or_create(organisation=org, user=fixture)
            for index in range(max(1, count)):
                project, _ = Project.objects.get_or_create(organisation=org, name=f"{label.title()} project {index + 1}")
                ProjectMembership.objects.get_or_create(project=project, organisation_membership=member)
            week = timezone.now().date() - timedelta(days=timezone.now().weekday())
            if count and not WeeklyWindow.objects.filter(organisation=org, week_start=week).exists():
                create_weekly_window(organisation=org, week_start=week, timezone_name="UTC")
            self.stdout.write(f"Synthetic journey ready: {name} / synthetic-review-password")
