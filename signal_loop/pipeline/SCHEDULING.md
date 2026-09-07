# Periodic dispatcher (#24)

`configure_schedule(organisation_id, timezone_name)` records an explicitly chosen
IANA timezone. `dispatch_due()` plans work then drains the PostgreSQL outbox;
Celery beat invokes it every 60 seconds. Queue arguments contain only an opaque
work reference, never source lists, feedback or contributor identity.

## Opening and closure

The dispatcher creates only the currently open local Monday-to-Monday window,
using #12's independently converted UTC boundaries and exclusive closing instant.
The user approved late capture from current membership while a missing window is
still open. `captured_late` records a new late materialization; false does not
attest legacy snapshot timing. Closed missing weeks are never reconstructed.
Future snapshots are not created early. Project scope freezes at materialization,
including projects with no members/responses. Later projects stay out of old scope.
Already-materialized windows catch up at closure within raw retention. Legacy
windows without dispatch scope queue known organisation projects plus captured
historical projects, including empty work scopes. This does not fabricate any
historical membership or contribution: eligibility remains the existing snapshot
and unavailable inputs remain unavailable. Disabled schedules do not plan new work.

The transaction locks organisation first, then closed WeeklyWindow rows in ID
order, matching #21. It reads scope-local anonymous source references only after
that same window lock, committing the frozen manifest and unique job together.
Admissions verified before close therefore finish before freezing; #21 rejects
at-close admission. A later sixth source cannot refresh a frozen manifest. The
analysis-owned selector imports no identity or participant models.

## Durable recovery and deadlines

`DispatchJob` has a UUID and either one invitation window or one
project/local-week/analysis-version key. Database constraints prevent duplicate
logical jobs; `WindowDispatch.frozen` prevents another closure snapshot.
`analysis1-privacy1-fake1` is a job version, not an invented aggregate schema.

Logical analysis expiry is the minimum of close+14 days and each source's original
expiry. Missing/withdrawn refs withhold before the handler. Invitations expire at
window close. Catch-up never resets those deadlines. Each broker publication has
its own maximum 24-hour expiry, capped by the logical job deadline; #23 preserves
that task deadline across retries. Durable work can recover after a longer outage
while still inside its original source lifetime.

The outbox commits a 30-second enqueue lease before transport. Crash before send:
the row remains. Accepted-but-unacknowledged send: the same reference may be sent
again after lease expiry. Queued jobs redrive after 60 seconds until terminal,
covering Redis loss. Active two-minute handler leases exclude concurrent workers;
completion uses the current run token, preventing a stale worker overwrite.
Crashes after handler effects require owned idempotency: the fake is harmless;
invitations use #22's committed delivery claims. No exactly-once broker/mail claim.

Invitation jobs invoke real `send_window_invitations`. Definite failures and
unresolved contacts retry the same window; SENT skips and ambiguous sends stay
quarantined. Celery completion is transport completion: inspect durable job state.
Fake analysis always records `unavailable`, including zero submissions. It never
calls AI or publishes. #33 owns the real pipeline and its idempotency guarantees.
Restricted refs remain only in PostgreSQL, not logs/status/Redis arguments.
Expired manifests are erased for terminal and pending jobs on dispatcher ticks;
handler access fails closed at the deadline. #38 owns broader physical/replica
retention enforcement.

Dispatcher limits are 30s soft/40s hard; scheduled jobs are 60s/90s. Redis visibility
is 120s and worker graceful stop is 100s. Handler lease is 120s, longer than an
attempt. Safe task retries remain bounded; durable outbox state is authoritative.
Planning counters are added only after commit.

## Local commands

PowerShell, repository root, after configuring the existing local services:

```powershell
uv run --env-file .env python manage.py migrate
# Use the explicitly provisioned organisation ID and timezone.
uv run --env-file .env python manage.py configure_schedule 123 Australia/Brisbane
$schedulerCompose = @('-p', 'signal-loop', '--env-file', '.env', '-f', 'compose.yaml', '-f', 'compose.worker.yaml')
docker compose @schedulerCompose --profile worker up -d --build worker beat
uv run --env-file .env python manage.py dispatch_due
uv run --env-file .env python manage.py dispatch_status 1ce42343-6b86-4d5d-9edf-c1053e986a34
docker compose @schedulerCompose logs --tail 30 beat worker
docker compose @schedulerCompose stop beat
docker compose @schedulerCompose stop worker
```

Use the same project/env as existing services (`signal-loop-issue1`/`.env.issue1`
for the review setup). Cached builds normally take under a minute; stop on build
or service-health failure. Dispatch prints safe counts; status returns only job
UUID/state, never manifest/participants. Broker failure leaves the outbox intact:
restore Redis, wait out its lease and rerun. Never flush Redis or reset terminal
delivery/job states as a shortcut. Operationally run one beat; database idempotency
also protects against an accidental second dispatcher. #42 owns deployment.

## Synthetic real beat/worker review

```powershell
uv run --env-file .env.issue1 python manage.py seed_dispatch_review --settings=signal_loop.settings_invitation_review
$env:WORKER_DJANGO_SETTINGS_MODULE = 'signal_loop.settings_worker_review'
$schedulerCompose = @('-p', 'signal-loop-issue1', '--env-file', '.env.issue1', '-f', 'compose.yaml', '-f', 'compose.worker.yaml')
docker compose @schedulerCompose --profile worker up -d --no-deps --build worker beat
# Allow at most 30 seconds for review ticks, then inspect safe logs/job state.
docker compose @schedulerCompose logs --tail 30 beat worker
docker compose @schedulerCompose stop beat
Remove-Item Env:WORKER_DJANGO_SETTINGS_MODULE
```

Review settings force console mail and a two-second cadence. The seed explicitly
creates a synthetic prior-window fixture (never production catch-up), plus #22's
current two-project aliases. Expect one completed invitation job and one unavailable
analysis job per prior project. Repeated ticks create no new jobs. Beat stays
stopped afterward; recreate services without the override to restore 60-second
cadence/default fail-closed providers. No external mail or deployment is authorized.

Focused tests: `uv run --env-file .env.issue1 pytest --postgres signal_loop/pipeline/tests`.
