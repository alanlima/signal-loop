# Local Celery worker

For weekly windows, durable outbox recovery and beat commands, see
[periodic scheduling](SCHEDULING.md).

Celery 5.6.3 and its compatible Redis client are locked in `uv.lock`. Django
settings configure JSON-only messages, Redis broker/results and the explicit
`signal-loop-local` queue. The harmless tasks do no business writes or external
delivery. #24 owns scheduling; #33 owns durable stage leases and idempotency.

Use Linux prefork, including Docker Desktop Linux containers on Windows.
[Celery does not support Windows](https://docs.celeryq.dev/en/stable/getting-started/introduction.html);
its [concurrency guidance](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html)
recommends prefork and notes missing timeout features in alternative pools.
Native Windows solo/eager tests are not evidence of bounded worker execution.

## Start, observe and stop

From the repository root in PowerShell, after configuring `.env` per root README:

```powershell
uv sync --locked
$workerCompose = @('-p', 'signal-loop', '--env-file', '.env', '-f', 'compose.yaml', '-f', 'compose.worker.yaml')
docker compose @workerCompose up -d --wait --wait-timeout 120 postgres redis
docker compose @workerCompose --profile worker up -d --build worker
uv run --env-file .env python -m signal_loop.pipeline.cli ping
uv run --env-file .env python -m signal_loop.pipeline.verify_worker
docker compose @workerCompose logs --tail 40 worker
```

The first build may take several minutes to download Python/build tools. Subsequent
builds reuse locked dependency layers. Stop on build failure, failed service health
or `broker_unavailable`; do not keep resubmitting. The image contains no `.env`,
repository history or credentials; its worker runs as an unprivileged user.
The worker command is exactly `celery -A signal_loop worker --pool=prefork
--concurrency=1 --loglevel=INFO --without-gossip --without-mingle --without-heartbeat`.
The container uses `signal_loop.settings_worker` for internal service addresses;
the host publisher uses the `.env` loopback ports.

Use the **same Compose project name and env file as the existing services**.
For the isolated review services that means `signal-loop-issue1` and `.env.issue1`
in both the array and uv commands. To add just the worker to healthy existing
services, use `up -d --no-deps --build worker`. Do not start another project on
the same bound ports. No production configuration/deployment is provided.

The live verifier sends four random opaque job references and polls for at most
35 seconds: normal completion, transient retry then completion, permanent failure
and a task interrupted by the real 5-second soft time limit. Success prints
`{"code":"verified","jobs":{...},"elapsed_seconds":...}`. It uses real Redis
and a separate prefork process, never eager mode. A missing worker times out.

Individual operations (replace the synthetic UUID with the returned job):

```powershell
uv run --env-file .env python -m signal_loop.pipeline.cli send --kind complete
uv run --env-file .env python -m signal_loop.pipeline.cli status --job 1ce42343-6b86-4d5d-9edf-c1053e986a34
uv run --env-file .env python -m signal_loop.pipeline.cli send --kind failure
docker compose @workerCompose logs --tail 100 worker
docker compose @workerCompose stop worker
docker compose @workerCompose stop postgres redis
```

`stop worker` leaves services/data intact; its 100-second graceful stop exceeds the
90-second maximum scheduled-job limit. Start again with `up -d worker`. Do not use broad
Redis flushes or delete PostgreSQL volumes to retry a task.

## Bounds, failures and retry contract

Smoke defaults are 5 seconds soft / 8 seconds hard, two retries maximum with 1 then 2
second backoff for **RetryableFailure only**. Timeouts and unknown/permanent errors
do not retry. The smoke retry fixture fails transiently once. A soft timeout is
reported as `timeout`; hard worker loss becomes `worker_failed`, without automatic
worker-loss requeue loops. Redis visibility timeout is 120 seconds, larger than an
attempt; late acknowledgment still means delivery can duplicate. There is no
exactly-once broker guarantee. See [Redis delivery caveats](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html).

Task bodies accept exactly one canonical random UUIDv4 job reference. Publisher
and worker reject additional arguments, keywords or arbitrary strings. No response
text, user/project-member ID, admission credential or email enters task arguments.
Task IDs are opaque work references, not contributor IDs. Argument representations
are replaced; task events and remote control are disabled. The broker is trusted
local infrastructure, not an untrusted public request endpoint.

Publication has a fixed deadline at most 24 hours away, preserved by Celery retry.
The result backend atomically sets Redis PXAT to that original deadline; completion
and retries cannot reset it. Missing/expired deadlines do not write a result.
Expired queued tasks are rejected when consumed. Redis queue storage is disposable;
#38 still owns physical removal of unconsumed expired/dead-letter messages and
operational retention. No raw sources are queued; their stricter deadlines must
also be carried by future #33 job records.

SafeTask catches failures and returns **logical** `status=failed` with safe codes;
Celery itself records those handled outcomes as SUCCESS. The CLI interprets this
payload and never reports them as complete. Unexpected process/transport failures
can have Celery FAILURE/REVOKED states and map to `worker_failed`. Their stored
exception and traceback are sanitized. `pending_or_unknown` cannot distinguish
not yet executed, expired or nonexistent jobs; it is not success or proof of loss.

Worker formatting emits only `worker_event`, or a fixed code plus validated job
UUID. It does not format received-message text, exceptions, traceback, arguments
or provider output. The synthetic permanent failure contains a private sentinel;
the verifier should produce only `permanent_failure`, never the sentinel. Worker
startup shows local service/queue configuration; do not deploy these local settings
with production credentials. #38/#42 own broader infrastructure logging/isolation.

Use `cli ping` for a bounded connection check. `broker_unavailable` exits 2; inspect
service health and `.env` ports without printing secrets. For failed jobs, find the
returned UUID using `cli status` and the content-free worker logs. Do not assume a
timed-out publisher failed to enqueue: delivery can be ambiguous.

Only the four harmless smoke kinds are safe to repeat; they have no side effects.
An explicit repeat may use `send --kind complete --job <original-UUID>`, but a
previous terminal result remains cached and is not evidence of that later delivery.
Use a fresh smoke reference to verify new worker execution. Never apply this retry
rule to invitation delivery or analysis stages: their owning service must first
authorize retry using its durable idempotency/lease state. Do not replay arbitrary
Celery tasks or infer idempotency from reusing a task ID.

Focused checks: `uv run --env-file .env pytest --postgres signal_loop/pipeline/tests`.
