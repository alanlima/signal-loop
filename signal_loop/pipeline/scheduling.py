"""Local scheduling and durable outbox. Safe retry requires owned handler state."""
from datetime import timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from signal_loop.analysis.aggregation import freeze_source_references, source_reference_expiry
from signal_loop.invitations.services import send_window_invitations
from signal_loop.membership.models import Organisation, Project
from signal_loop.windows.models import EligibilitySnapshot, WeeklyWindow
from signal_loop.windows.services import create_weekly_window

from .models import DispatchJob, OrganisationSchedule, WindowDispatch


VERSION = "analysis1-privacy1-fake1"
TERMINAL = {"complete", "unavailable", "expired"}


def configure_schedule(*, organisation_id, timezone_name):
    with transaction.atomic():
        Organisation.objects.select_for_update().get(pk=organisation_id)
        schedule = OrganisationSchedule.objects.filter(organisation_id=organisation_id).first()
        if schedule is None:
            schedule = OrganisationSchedule(organisation_id=organisation_id)
        schedule.timezone_name = timezone_name
        schedule.enabled = True
        schedule.save()
        return schedule


def _create_job(window, kind, at, *, project=None, sources=(), expiry=None):
    return DispatchJob.objects.get_or_create(
        kind=kind, window=window, project_id=project, week=window.week_start, version=VERSION,
        defaults={"frozen_sources": list(sources), "enqueue_after": at,
                  "expires_at": expiry or window.closes_at + timedelta(days=14)
                  if kind == "analysis" else window.closes_at},
    )[1]


def plan_due(*, clock=timezone.now):
    counts = dict(opened=0, closed=0, jobs=0, failed=0)
    for schedule in OrganisationSchedule.objects.filter(enabled=True).order_by("organisation_id"):
        committed = dict(opened=0, closed=0, jobs=0)
        try:
            with transaction.atomic():
                org = Organisation.objects.select_for_update().get(pk=schedule.organisation_id)
                at = clock()
                if timezone.is_naive(at):
                    raise ValueError("invalid_clock")
                if org.is_active:
                    day = at.astimezone(ZoneInfo(schedule.timezone_name)).date()
                    week = day - timedelta(days=day.weekday())
                    window = WeeklyWindow.objects.filter(organisation=org, week_start=week).first()
                    captured_now = window is None
                    if window is None:
                        window = create_weekly_window(organisation=org, week_start=week, timezone_name=schedule.timezone_name)
                        committed["opened"] += 1
                    # Only the currently open missing week is captured late. Never
                    # backfill already-closed historical membership snapshots.
                    if window.opens_at <= at < window.closes_at:
                        record, _ = WindowDispatch.objects.get_or_create(
                            window=window, defaults={"captured_late": captured_now and at > window.opens_at,
                                "projects": list(Project.objects.filter(organisation=org, is_active=True).values_list("pk", flat=True))},
                        )
                        committed["jobs"] += _create_job(window, "invitation", at)
                windows = WeeklyWindow.objects.select_for_update().filter(
                    organisation=org, closes_at__lte=at, closes_at__gt=at - timedelta(days=14),
                ).order_by("pk")
                for closed in windows:
                    record = WindowDispatch.objects.filter(window=closed).first()
                    if record is None:
                        # Legacy windows lack a dispatch project manifest. Queue
                        # known organisation projects plus captured historical ones;
                        # this creates work scope, never eligibility/membership.
                        projects = sorted(set(EligibilitySnapshot.objects.filter(window=closed).values_list("membership__project_id", flat=True))
                                          | set(Project.objects.filter(organisation=org).values_list("pk", flat=True)))
                        record = WindowDispatch.objects.create(window=closed, projects=projects)
                    if record.frozen:
                        continue
                    for project in record.projects:
                        sources = freeze_source_references(project_id=project, week=closed.week_start)
                        expiry = source_reference_expiry(project_id=project, week=closed.week_start,
                                                         references=sources, empty_expiry=closed.closes_at + timedelta(days=14))
                        if expiry is None:
                            raise ValueError("source_unavailable")
                        committed["jobs"] += _create_job(closed, "analysis", at, project=project, sources=sources, expiry=expiry)
                    record.frozen = True
                    record.save(update_fields=["frozen"])
                    committed["closed"] += 1
            for key, value in committed.items():
                counts[key] += value
        except Exception:
            counts["failed"] += 1
    return counts


def publish_job(kind, reference, expiry):
    from .tasks import scheduled_job
    scheduled_job.apply_async(args=[reference], expires=min(expiry, timezone.now() + timedelta(hours=24)), retry=False)


def enqueue_due(*, clock=timezone.now, publisher=publish_job):
    counts = dict(queued=0, failed=0, expired=0)
    at = clock()
    ids = list(DispatchJob.objects.exclude(state__in=TERMINAL).filter(enqueue_after__lte=at).values_list("pk", flat=True))
    for identifier in ids:
        with transaction.atomic():
            job = DispatchJob.objects.select_for_update().get(pk=identifier)
            at = clock()
            if job.state in TERMINAL:
                continue
            if job.expires_at <= at:
                job.state = "expired"
                job.frozen_sources = []
                job.save(update_fields=["state", "frozen_sources"])
                counts["expired"] += 1
                continue
            if ((job.enqueue_lease_until and job.enqueue_lease_until > at)
                    or (job.run_lease_until and job.run_lease_until > at)):
                continue
            job.enqueue_lease_until = at + timedelta(seconds=30)
            job.save(update_fields=["enqueue_lease_until"])
        try:
            publisher(job.kind, str(job.pk), job.expires_at)
        except Exception:
            counts["failed"] += 1
            continue  # Original committed outbox row remains recoverable after lease.
        DispatchJob.objects.filter(pk=identifier).exclude(state__in=TERMINAL | {"running"}).update(
            state="queued", enqueue_after=at + timedelta(seconds=60), enqueue_lease_until=None,
        )
        counts["queued"] += 1
    return counts


def dispatch_due(*, clock=timezone.now, publisher=publish_job):
    expire_source_references(at=clock())
    return {"planning": plan_due(clock=clock), "outbox": enqueue_due(clock=clock, publisher=publisher)}


def expire_source_references(*, at):
    """All terminal and pending restricted manifests obey the original deadline."""
    DispatchJob.objects.filter(expires_at__lte=at).exclude(frozen_sources=[]).update(frozen_sources=[])


def fake_analysis(job):
    # #33 is not implemented. No eligible proof/provider, so even nonempty input
    # remains uniformly unavailable; zero submissions never fabricate a report.
    return "unavailable"


def run_job(reference, *, clock=timezone.now, invitation_service=send_window_invitations, analysis_handler=fake_analysis):
    try:
        identifier = UUID(reference)
        with transaction.atomic():
            job = DispatchJob.objects.select_for_update().get(pk=identifier)
            at = clock()
            if job.state in TERMINAL:
                return job.state
            if job.expires_at <= at:
                job.state = "expired"
                job.frozen_sources = []
                job.save(update_fields=["state", "frozen_sources"])
                return "expired"
            if job.kind == "analysis" and job.window.closes_at > at:
                return "pending"
            if job.kind == "analysis":
                expiry = source_reference_expiry(project_id=job.project_id, week=job.week,
                                                 references=job.frozen_sources, empty_expiry=job.expires_at)
                if expiry is None or expiry <= at:
                    job.state = "unavailable"
                    job.frozen_sources = []
                    job.save(update_fields=["state", "frozen_sources"])
                    return "unavailable"
            if job.run_lease_until and job.run_lease_until > at:
                return "running"
            job.state = "running"
            job.run_token = uuid4()
            job.run_lease_until = at + timedelta(minutes=2)
            job.save(update_fields=["state", "run_token", "run_lease_until"])
        if job.kind == "invitation":
            outcome = invitation_service(window_id=job.window_id, clock=clock)
            state = "complete" if outcome.get("code") == "complete" and not (outcome.get("failed") or outcome.get("withheld")) else "pending"
        else:
            state = analysis_handler(job)
            if state not in {"complete", "unavailable"}:
                state = "pending"
        DispatchJob.objects.filter(pk=identifier, run_token=job.run_token, state="running").update(
            state=state, run_token=None, run_lease_until=None, enqueue_after=clock() + timedelta(seconds=60),
        )
        return state
    except Exception:
        return "retry_pending"  # Claim lease expires; no exception/body reaches logs.
