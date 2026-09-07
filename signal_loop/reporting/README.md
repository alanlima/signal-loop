# Reporting ownership and manager composition

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
