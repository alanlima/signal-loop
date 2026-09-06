# Anonymous project feedback persistence (#15)

`persist_sections(sections)` is a trusted transaction-participating sink for the
[#13 protocol](../../_docs/anonymous-submission.md), not a public submission API.
It returns only `complete` or `no_feedback`, or raises `PersistenceError` with a
fixed `invalid_submission`/`persistence_failed` code. It returns no row/source IDs.
#21 must invoke it inside the admission transaction that authenticates, checks
verified-person eligibility, redeems credentials once and deletes the draft.
Direct repeated sink calls are not idempotent: exactly-once admission belongs to
#14/#21, not a stored identity/credential/body-hash key in feedback.

## Stored shape and privacy review

Each `FeedbackSection` stores exactly:

| Field | Meaning |
| --- | --- |
| `id` | Independently generated random UUID4, restricted source reference within the project/week |
| `project_id` | Internal project scope integer; no relation to a person |
| `week` | Organisation-local Monday date, never the global journey week |
| `schema`, `privacy_policy` | Supported `project-feedback/1.0` and `1.0` |
| `answers` | Validated J1/J2/J3 and permitted F1/F2 values only |
| `expires_at` | Public local-window closing instant plus fourteen elapsed days, stored UTC |

There are no foreign keys, user/account/member/principal identifiers, credentials,
participation references, draft/batch/journey IDs, payload fingerprints, creation
or update timestamps, response ordering counters, personal fields or cross-project
links. Each multi-project request produces independent rows without a durable
parent object. Schema introspection tests prove no foreign keys; source checks
prevent direct membership/admission/auth imports into feedback modules.

No personal representation is stored: P1-P5 are private transient reflection and
are forbidden at this sink. Identifying text voluntarily entered into a project
answer is still restricted raw content; storing it does not make it safe to
publish. #4 content/support/inference gates remain mandatory. Random IDs and absent
application joins do not eliminate privileged database/timing correlation; #42's
operational separation and no-raw-backup clearance remain required.

There is no admin registration, default model permission, raw-feedback endpoint
or product export. Supported direct save/update/bulk-write APIs reject writes;
the validated service alone invokes the private insertion path. Restricted workers
must enforce scope/expiry through their future interfaces. Scheduled deletion,
withdrawal and replica/backup enforcement belong to #38/#42. No source expires
later because of retries or edits, and no exact submission time is recorded.

## Validation and window context

Input matches #14's sink dictionaries exactly: `project`, `week`, `schema`,
`privacy_policy`, `answers`. Unknown envelope or answer keys reject the entire
request, including personal fields and arbitrary nested JSON. Versions must match
exactly; project IDs are positive signed-64-bit integers (not booleans), and weeks
must be canonical local Monday ISO dates. One request has 1-3 distinct projects.

The pure `signal_loop.contracts.feedback` validator is shared with admission:
J1/J2 require the exact #5 enums, with no defaults; J3 allows 0-320 Unicode code
points; F1/F2 allow 0-240. CRLF/CR normalize to LF before counting, without trimming,
truncating or mutating caller input. At most one follow-up key per project and two
total are permitted, with the appropriate J1/J2 trigger. #20/#21 additionally prove
offered-question history, allocation order, draft revisions, and removal consent;
the sink does not invent those facts from answer text.

Whitespace-only optional text remains semantically blank and supplies no evidence.
A wholly declined/unknown and blank project section is omitted without a row or
neutral score; substantive siblings can persist. All-non-substantive input returns
`no_feedback`. A valid declined choice remains declined even when substantive text
exists. Input over a limit fails without truncation; draft recovery is #16/#21.

`windows.services.project_week_scope` exposes only project ID, local week and public
open/close instants. The sink uses it to reject unknown/mismatched windows and to
derive expiry, without querying eligibility or identity. A project/schedule match
is not participant authorization; that has already been established by admission.
The sink checks aware server time against `[open, close)` before validation writes
and again after preparation. `clock` is an internal deterministic test seam, never
a caller-supplied timestamp from a request. Closed or missing context fails closed.

## Atomicity and verification

All sections/scopes validate before the first insertion. A single Django
transaction inserts every substantive section. Failure after an earlier insertion
rolls back the entire set; when called inside admission, the same outer transaction
also owns credential consumption and draft deletion. No independent commit,
external call, log of content or response ID is emitted by this sink.

```powershell
uv run --env-file .env.issue1 pytest --postgres signal_loop/feedback/tests signal_loop/admission/tests
uv run --env-file .env.issue1 pytest --postgres
uv run ruff check .
uv run --env-file .env.issue1 python manage.py makemigrations --check --dry-run
```

Substitute your configured disposable environment-file path. Tests inspect actual
PostgreSQL columns/constraints and synthetic rows; reject unknown/personal/nested
fields, bad enum/type/version/scope and excessive text/followups; preserve exact
Unicode/newline/blank semantics; prove rollback after first row and outer-transaction
failure; and confirm #14 behavior through its complete regression suite. No new
dependency or database extension is required. Production collection remains gated
by #13 R1-R5; this issue adds no admission bypass or publication capability.
