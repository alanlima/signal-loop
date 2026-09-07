# Reporting ownership and manager composition

## Independent team summary (#32)

`team.compose_team(TeamInput(eligible, themes, recommendations=None, history=None),
project=..., week=..., version=..., closes_at=..., at=..., context_provider=...,
commitment_provider=None)` owns the separate `TeamSummary` candidate and team
release. It accepts actual restricted #25/#26 wrappers directly: a manager report,
scored issue or recommendation is not needed for team eligibility. Its independent
gate checks current scope/expiry, five distinct contributors and five actually
grounded supporters for every selected theme. Unknown or unsupported themes fail
closed. An explicit empty theme set or missing input/context suppresses. Neither
failure stores a partial canonical artifact or public summary.

The bounded team wording catalog covers the #29 concern categories plus the
shared milestone win and shared backlog support need. It produces independently
supported paraphrases, never raw participant quotations. Major themes, wins,
blockers and shared concerns occupy the exact canonical themes array; no invented
schema fields or sentiment/morale inference are introduced. Trends are optional:
the explicit `SeverityHistory` handoff is recomputed through #27 against the actual
two weeks and its bound independent history reviewer. Missing history means an
explicit empty trends array; supplied unsafe history withholds the whole summary.

Optional #30 recommendations select only literal `suggest_for_team=True` actions.
Each selected action is independently matched to its grounded theme and at least
five actual supporters. Process suggestions are normative options, not assertions
that participants already proposed them. Private recommendations, rationale,
severity and scoring explanations are never copied. Empty focus and commitments
are explicit arrays. The gate never constructs team JSON by redacting manager JSON.

`TeamPublicationContext(joint_context, manager_recommendations, manager_context)`
comes from a trusted complete server inventory. Both manager fields explicitly
`None` mean known absence, not an inferred default. A present manager supplies the
actual #30 wrapper and `PublicationContext` snapshot, which #31's pure gate
independently recomputes; the actual current source set and joint inventory must
match. The team gate separately reviews the complete source/context inventory and
its own finite safe clauses. Under the shared project/week transaction lock, any
existing manager release must equal that exact reviewed manager content and be
ready/unexpired. Missing, withdrawn, expired or changed counterpart evidence
withholds team release; its expiry also bounds team retention. The context is
reloaded before persistence and elapsed review/lock time consumes source lifetime.
No production inventory provider or pipeline wiring is implemented here.

The optional #36 fixture boundary is `commitment_provider.published_for(project,
week)` returning a tuple of `PublishedCommitment(project, week, text, published_at,
expires_at)`. This server-owned interface represents records **already published**
through the commitment workflow, not model `approved` flags or draft records. The
team gate checks scope, publication time, expiry and a grounded safe process-action
catalog; it reloads the same records before writing. Unknown wording fails closed.
The fixture boundary creates no approval or commitment record. Canonical approved
flags are derived only after those checks; public commitments are plain safe text.
#36 remains responsible for the real authorized publication selector. A previously
released manager still uses #31's empty-commitment counterpart boundary; new joint
manager composition with commitments remains fail-closed until its verified handoff.

`TeamSummary` stores the exact restricted `team-summary/1.0` envelope keyed by
project/week/analysis version/schema/privacy policy, including only scoped theme
and trend references plus its own processing provenance. It never stores raw
feedback, issue references or manager-only fields. Candidate expiry is bounded by
the earliest supporting artifact. The separate `AudienceRelease` stores only exact
team `audience-release/1.0` content, without restricted references or provenance.
Candidate and release writes roll back together. Same-version retries reuse the
decision; the first project/week/team release is immutable across versions and
concurrent attempts. Withdrawal seals its slot. Safe release retention follows
#31's original-closure/history limits and cannot outlive a supporting commitment
or existing counterpart. #38 owns physical deletion.

`selectors.team_summary_for` enforces #9 team authorization before querying any
release and returns only the exact team envelope. Unauthorized, failed, suppressed,
withdrawn and expired summaries share the content-free unavailable response;
not-yet-available depends only on the public closing schedule. This issue adds no
UI, model provider calls, production publication job or later backlog wiring.

Focused team tests use real isolated PostgreSQL for atomicity, rollback, concurrent
versions, immutable releases, symmetric manager checks, expiry and selectors.
Pure fixtures cover all required theme types and focus together, actual grounding,
history recalculation, private sentinels, invalid/unsafe input and the already
published commitment boundary. Run `uv run --env-file .env.engineer2 pytest
--postgres signal_loop/reporting/tests/test_team.py` with the isolated engineer
environment (or the corresponding local QA environment).

`services.compose_manager(recommendations, project=..., week=..., version=...,
closes_at=..., at=..., context_provider=...)` accepts the implemented #30
`RestrictedRecommendations` handoff. The service snapshots its complete lineage,
independently checks canonical #6 artifacts, actual whole-source grounding,
distinct report/item support, severity arithmetic and supported impact/urgency,
qualitative history, safe evidence and recommendation relevance/rationale. It
does not call a model or query identities. Missing input/context or empty supported
output suppresses; invalid/unsafe lineage fails closed. Neither returns partial
reader content. The precise internal state is never a reader response.

`composition.prepare_manager` is the pure gate. A complete positive synthetic
fixture traverses the actual #28/#29/#30 services. The reviewed vocabulary is
deliberately bounded to their supported catalog; unknown claims are withheld.
The canonical `manager-report/1.0` candidate contains validated scoped references,
title/overview and restricted processing provenance. Its expiry is the earliest
underlying source/artifact expiry, including historical sources. Candidate rows
never store entire feedback, identities, credentials or contributor records.

The separate manager projection has the exact `audience-release/1.0` content
fields. Themes and overview use independently grounded paraphrases. Severity is
accompanied by supported, nonnumeric paraphrases of impact/urgency; the numeric
scoring explanation is never copied. Trends are qualitative. Evidence retains
the exact synthesis label. Recommendations expose only action/rationale, without
the internal team suggestion flag. The no-verbatim-excerpt check applies across
all displayed factual text. Counts, source IDs, policy badges, provenance and
reasons never reach the display serializer.

## Joint audience boundary and #32 handoff

`PublicationContext(joint_context, team_content)` is a trusted server-injected
inventory plus an independently composed team candidate, not model approval.
`context_provider.load(project=..., week=...)` must return the current complete
inventory; it is compared to #30's exact snapshot and reloaded before persistence.
Unknown, changed or incomplete review withholds. Under the same scope lock, an
existing team release must exactly match the reviewed team candidate and remain
ready/unexpired; otherwise manager release is withheld. Its earlier expiry also
bounds the new manager release. The manager gate independently
checks the exact team fields and every team overview/theme/trend/focus against
the supported material, including team-flagged normative actions. Team JSON must
not contain manager-only fields. It is not constructed by hiding manager fields.
This stage accepts no commitments until #36 supplies an independently verified
approval/safety handoff. No production context provider is invented; tests supply
an explicit synthetic team candidate until #32/#33 wire the real boundary.

#32 owns its separate `TeamSummary` candidate/model and composition gate. Shared
storage interfaces are `models.AudienceRelease` and these internal functions:

- `lock_project_week(project, week)` requires `transaction.atomic()` and takes the
  same PostgreSQL advisory transaction lock for both audiences.
- `publish_locked(project=..., week=..., audience=..., content=..., at=...,
  expires_at=...)` is persistence only **after** the caller's independent audience
  and joint gates. Correct JSON shape is not privacy approval. Both audience gates
  must review the actual counterpart candidate and already released content.
- `withdraw_release(project=..., week=..., audience=...)` removes the entire
  original safe content. It cannot replace text or reopen that audience's slot.

No UI or workflow task is added here. #34 must use `selectors.manager_report_for`
with the real project, public window boundary and current clock. It enforces #9
manager authorization before reading a safe release; it never reads candidates.
Unauthorized/unavailable/failed/withdrawn/expired cases have no content. The
pre-closure status depends only on the public schedule. #32 adds its own scoped
team selector using the same exact audience envelope, not a manager projection.

## Durable keys, deadlines and failures

`ManagerReport` is unique by project/week/analysis version/schema/privacy version.
Duplicate deliveries reuse the same decision and record. `AudienceRelease` is
unique by project/week/audience **across all versions**; the safe content and
publication time are immutable. A new analysis version cannot replace or refresh
an existing release, including a withdrawn release. Ordinary duplicate delivery
also reuses a failed/suppressed candidate; explicit controlled retry transitions
belong to #33, within the original expiry and before any release.

Candidate creation and first safe release are one PostgreSQL transaction under
the shared scope lock. Database failure rolls back both; another attempt can
safely retry. Supported model/queryset/admin mutation paths cannot edit/delete
these records. No reporting admin is registered. The validated internal service
boundary, not possession of a JSON object, owns writes.

Elapsed composition/lock time, including the final context reload, counts against
the original source deadline. Safe
output retention is at most 365 days and conservatively bounded by original
closure; reports with consecutive-week trends use the preceding closure bound,
so historical derivatives cannot restart the older release's lifetime. Source
expiry blocks new generation, but already approved safe output can remain until
its separate release expiry. Selectors enforce expiry immediately. #38 owns
physical expiry/deletion and backup enforcement; this issue does not claim a
running deletion worker or production release clearance.

Validation: `uv run --env-file .env.issue1 pytest --postgres
signal_loop/reporting/tests` uses a disposable PostgreSQL test database. Fixtures
cover exact canonical storage/serialization, actual multi-stage lineage, source
contradictions, unsafe/joint-context changes, empty/suppressed/failed cases,
immutable retries across versions, concurrent first release, rollback, withdrawal,
authorization, original deadlines and safe retention. No external provider or
delivery is used.
