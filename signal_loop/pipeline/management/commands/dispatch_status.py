import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from signal_loop.pipeline.models import DispatchJob


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("job")

    def handle(self, *args, **options):
        try:
            identifier = UUID(options["job"])
            job = DispatchJob.objects.get(pk=identifier)
        except Exception:
            raise CommandError("job_unavailable") from None
        self.stdout.write(json.dumps({"job": str(job.pk), "state": job.state}))
