from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from signal_loop.membership.models import Organisation, OrganisationMembership, Project, ProjectMembership
from signal_loop.windows.models import WeeklyWindow
from signal_loop.windows.services import create_weekly_window


class Command(BaseCommand):
    help = "Create synthetic invitation-only fixtures under explicit local review settings."

    def handle(self, *args, **options):
        if not getattr(settings, "INVITATION_REVIEW_MODE", False):
            raise CommandError("synthetic_review_settings_required")
        org, _ = Organisation.objects.get_or_create(name="Synthetic invitation review")
        for name in ("Cedar", "Birch"):
            project, _ = Project.objects.get_or_create(organisation=org, name=name)
            for username in ("synthetic_invitation_rowan", "synthetic_invitation_alias", "synthetic_invitation_avery"):
                user, _ = get_user_model().objects.get_or_create(username=username, defaults={"is_active": True})
                membership, _ = OrganisationMembership.objects.get_or_create(organisation=org, user=user)
                ProjectMembership.objects.get_or_create(project=project, organisation_membership=membership)
        day = timezone.now().date()
        week = day - timedelta(days=day.weekday())
        window = WeeklyWindow.objects.filter(organisation=org, week_start=week).first()
        if window is None:
            window = create_weekly_window(organisation=org, week_start=week, timezone_name="UTC")
        self.stdout.write(f"synthetic_window={window.pk}")
