# Atomic final submission (#21)

The real authenticated endpoint is `POST /app/check-in/submit/`. The browser sends
only CSRF, the saved draft revision and global UTC journey week. Answers come from
the owned private draft; a client cannot attach arbitrary sections, IDs, credentials
or alternate answers at final POST. The finish view now offers **Submit check-in**.
All edited fields must be saved first; the existing unsaved-form guard prevents
accidentally submitting other forms while typed edits remain unsaved.

`submit_check_in` in this module orchestrates the existing admission and anonymous
sink services. Private draft callbacks stay in `checkins/submission.py`, which
locks/revalidates revision, retained scopes, original expiry, current eligibility,
seen J fields, resolved/excluded F answers and substantive content. P1-P5 are
validated privately where required, then omitted completely from the payload.
Hidden stale rows cannot bypass the seen-question boundary.

## Transaction and credential boundary

Begin does not persist plaintext credentials. Admission `refresh_credentials`
rotates independent ephemeral secrets for only the retained scopes of an existing
open journey. It cannot begin a new journey, replace selection, extend expiry or
refresh expired/cancelled/consumed credentials. Omitting an acknowledged revoked
section therefore does not require reissuing its credential. No secret is sent to
the browser, logged, attached to feedback or stored in a draft.

One outer PostgreSQL transaction holds the existing deterministic admission locks
through refresh, fresh private-draft validation, redemption, canonical anonymous
insertion, complete draft deletion and journey sealing. Any failure rolls back
verifier rotation, participation consumption, inserted rows, cleanup and completion.
The sink uses the same connection and returns a generic result without source IDs.
Every stored row is the exact canonical `feedback/1.0` artifact from #6; each has an
independent source UUID, with no personal/identity/credential/draft/batch fields.

Success consumes only substantive submitted participation, cancels remaining
credentials, clears transient admission selection/start/expiry and deletes the
entire private draft, including project/adaptive/personal state. An all-omitted or
all-non-substantive payload returns `no_feedback` and retains the review/discard
path without consumption/completion. Stale revisions fail without overwriting
saved answers. A fresh request at hard expiry seals/erases expired private state.

Double clicks/concurrent requests serialize on admission locks. Rejected repeat
redemption is reconciled through the authenticated principal/global-week
`own_status`, never a feedback lookup. Fresh success and already-completed replay
both render exactly `Your check-in is complete.` The POST retains the original
global week so a lost response can be reconciled after local-window or credential
expiry, within admission's status retention. Response templates contain no feedback
or source IDs, raw text, contributor counts, credentials or exception details.

## Admission instant and #24 closure handoff

Admission verifies server time after locking and credential validation, immediately
before writes. Its new `admitted_sink(sections, admitted_at)` callback passes this
verified instant explicitly; the old `sink(sections)` API remains supported for
#14 fixtures. Exactly one sink callback is required. The real sink uses that frozen
instant for its open-window validation, so a request admitted before close may
finish its transaction afterward. A request admitted at close is refused.

Locks are acquired in order: relevant organisation rows by ID, WeeklyWindow rows
by ID, principal/current account/membership context, then participation/credential
rows by project ID. Draft validation/cleanup follows while these locks remain held.
The #24 closure worker **must acquire the same WeeklyWindow row lock in its
transaction before reading/fixing that window's input set**. When freezing several
windows, use the same ascending-ID order; any organisation locks must precede them.
Do not freeze an unlocked snapshot first or independently decide closure from a
wall clock while admission is in flight. Once the lock is acquired, the snapshot
includes committed pre-close admissions and excludes refused later admissions.
Closure processing remains idempotent by public project/week; no raw queue payload
or participant-submission event is emitted here. This is an implementation handoff,
not a claim that the future worker or production deployment exists.

A real PostgreSQL test blocks a freezer on that window lock, admits at close minus
one second, advances time beyond close while the sink waits, then commits and
demonstrates that the freezer sees the committed input exactly once.

## Verification and browser handoff

```powershell
uv run --env-file .env.issue1 pytest --postgres signal_loop/checkins/tests/test_submission.py
uv run --env-file .env.issue1 pytest --postgres
uv run ruff check .
```

Tests cover canonical writes/full cleanup, simultaneous HTTP requests, replay after
lost response/expiry, failure after the first of two inserts, cleanup failure after
both inserts, verifier rollback, acknowledged revoked-scope omission, stale/tampered
requests, expired credentials, exact closure, non-substantive payloads, CSRF/ownership,
and the authoritative unseen-field regression through the real endpoint.

No new migration/dependency is needed for #21. Restart the owned synthetic review
server at the committed version; use the accounts/setup in
[checkins/JOURNEY.md](../checkins/JOURNEY.md). Previously completed practice journeys
retain their drafts and can now submit saved answers. Check the real completion
page at360px with keyboard, then resubmit the captured revision/week and confirm the
same generic completion without another write. Successful real submission deletes
the draft and seals the week; the seed must not reset it. Only use synthetic text.

The old preview callback remains an explicitly configured test seam for #20
regressions. Its former action is refused unless `CHECKIN_FINAL_SUBMISSION` is set,
and no normal browser control points to it. It cannot be mistaken for a real
completed admission. Production principal/provider/retention deployment gates in
#38/#39/#42 remain unchanged; no external service or deployment is performed.
