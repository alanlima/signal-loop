# Restricted project-week aggregation

`aggregate(project, week, artifacts, closes_at, at, verifier, threshold=5)`
(keyword arguments) accepts complete canonical `feedback/1.0` envelopes from
`_docs/analysis-contracts.md` section 2. `aggregate_stored(project_id, week, at,
verifier, threshold=5)` reads the existing anonymous store and public schedule.
Both return `RestrictedAnalysisInput` or `Suppressed(status="unavailable")`.
No endpoint, model, migration, email, provider call or publication is introduced.

The restricted result preserves the complete validated envelopes and their
project-local source IDs, carries the minimum source expiry and verified internal
count, and makes defensive copies for analysis. Its representation hides content.
It is an in-process type, **not** an invented `aggregate/1.0` schema: #6 does not
define aggregate data fields. A persisted aggregate needs an explicitly reviewed
contract. #18 continues to use its existing `analysis-request/1.0` inputs; the
theme stage builds its request and scoped registry from these canonical
artifacts. #33 owns orchestration. #18 accepts at most 100 artifacts per request; larger input
sets need bounded pipeline batching without combining or inventing distinct
support. This service does not make that provider call. Never serialize this
result directly to a renderer.

Only closed, unexpired project-weeks qualify. Every source must be substantive,
unique, same-scope, supported policy/schema, and within the original 14-day raw
lifetime. Optional personal fields, unknown fields and unresolved provenance
references reject the whole input. P1-P5 never enter analysis and never fill
project defaults. One J/F section supplies at most one contributor, regardless
of question count. Roster size is deliberately absent from the counting API.
The default threshold is five; configuration may be stricter but cannot reduce it.

## Trusted evidence boundary

The server injects an `EvidenceVerifier`; no request JSON, model claim, UUID
count, email uniqueness or roster count is evidence. `assess` receives only one
scope's canonical anonymous artifacts and must return an `Assessment` tied to
the exact complete source set. It must independently establish that every source
was admitted as one eligible natural person under #13, with no alias, retry,
withdrawn or incomplete contribution inflation, and that content and joint
inference review are safe. Count must match that proven one-person-per-source
invariant. All checks must be explicitly true. A mismatched scope/set, uncertain
count, unsafe overlap, malformed result or exception suppresses everything.

The synthetic test verifier returns independently declared fixture evidence;
it is not a production implementation. There is no default production verifier.
Production remains fail-closed until #33/#42 wire and attest the enforced #13
admission/storage invariant and appropriate privacy review. They must not create
an identity-to-source map to implement this interface. Exact source-set binding
is ephemeral and project-local; no principal/account/roster/credential imports,
shared project keys, content hashes or persistent evidence records are added.
Review repeated identifying narratives against overlapping/current/prior release
context through the privacy boundary; lack of a detected attack is not proof.
The interface does not claim to perform that semantic review automatically.

## Downstream limits

Input eligibility is **not publication permission**. #26 extracts candidates;
#29 must verify five actual supporters of each factual claim, grounding, content
and inference safety; #31/#32 jointly gate both audience projections. Five
contributors discussing unrelated subjects never imply a five-support theme.
Suppressions contain no counts, reason distinctions, identities or feedback.
No exception diagnostics or raw text are logged by this service.

#24/#33 own closure freezing under the same window lock documented in
`../submission/README.md`; invoke this read-only boundary with that frozen set.
It does not persist, publish, revise or refresh an aggregate after a late response.
Expiry and withdrawals remain mandatory downstream; retries cannot extend the
minimum source expiry. #38 owns operational deletion.

Run `uv run --env-file .env.issue1 pytest --postgres signal_loop/analysis/tests`.
Fixtures cover threshold minus/at/plus one, sparse and small rosters, repeated
answers/follow-ups/aliases, overlapping identifying narratives, unknown evidence,
scope and personal-field rejection, expiry, safe suppression and real database
isolation. They use no external service or production data.

## Restricted theme extraction (#26)

`themes.extract_themes(eligible, closes_at=..., at=..., adapter=..., grounding=None)`
accepts the trusted in-process `RestrictedAnalysisInput` from this module. JSON,
raw lists, unknown types, invalid envelopes, duplicate sources, expired input,
less than five nonempty contributors and requests above #18's 100-source bound
fail before provider work. This is an internal Python boundary, not an
unforgeable capability: callers must obtain eligibility from #25, never construct
it from client input. The stage derives its reference registry from the actual
supplied sources; the provider cannot supply or enlarge it.

Only `Adapter.structured_analysis` makes provider calls. Success is a
`RestrictedThemes` containing exact `themes/1.0` (defensive access through
`artifact_for_analysis()`); adapter/validation failures are content-free
`ExtractionFailure` values. `Suppressed` passes through unchanged without a
provider call. Explicit trusted empty input returns a validated envelope with
`data={"items": []}` and no source refs or provider work. #25 currently suppresses
zero submissions, so this empty branch is a defensive internal handoff rather
than permission to bypass eligibility. A provider can also return zero items.
No empty result is an available report.

Output categories remain exactly `delivery`, `workload`, `collaboration`, `wins`,
`support`. Recurring concerns retain their subject category; this stage cannot
invent a historical comparison or emit `recurring_concern` as a theme category.
It produces candidates for #28, not `issues/1.0` severity objects. Every referenced
source must support the whole statement. After grounding, its support count must
match the #25-proven one-person-per-source invariant; a provider's count never
establishes that invariant. Candidates with fewer than five actual supporters
remain restricted. Output lifetime cannot exceed the earliest input expiry.

The built-in `ConservativeGrounding` is usable without another model: it checks
structured delivery/workload statements against exact enums and whole-field
extracts against the entire note or follow-up answer. It does not accept a
substring, keyword overlap, removed negation/context, unknown/declined enum as
evidence, or an invented paraphrase. Free-text category checking uses bounded
complete-sentence grammars for ordinary delivery, workload, collaboration, wins
and support statements; these classify an already exact source extract rather
than infer a stronger claim. For example, `Reviews are waiting in the queue.`
can be a delivery candidate; `Reviews are not waiting in the queue.` cannot
support it. `Review queues keep delaying delivery.` preserves the source's
recurring concern without inventing prior-week evidence.

This conservative verifier deliberately rejects many legitimate paraphrases
and unfamiliar categorized sentences. A full exact extract can remain
uncategorized, as permitted by #6. A server-injected `GroundingVerifier` can
extend semantic coverage, but must independently inspect actual source content,
check every factual clause and category, preserve negation/context, and return
an exact claim/category/source-set-bound `Grounding` result. Missing, partial,
foreign, malformed or exceptional evidence fails closed. An AI boolean, caller
count or source-ID-only lookup is not a production verifier. #33 owns selecting
and documenting any such extension; #39 still owns any vendor and verified
production processing. None is silently selected here.

`THEME_INSTRUCTIONS` is the fixed trusted prompt contract for #39's eventual
provider wrapper to select for `analysis-request/1.0 -> themes/1.0`; it is not an
extra request field or concatenated feedback instruction. #18's exact request
envelope remains unchanged. Synthetic fake providers return explicit fixtures
and do not perform prompting. The runtime checks are independent of whether a
provider follows instructions: injected JSON, foreign refs, changed schemas and
unsupported claims reject. Source text remains data and is never executed.

Extractive theme text is restricted intermediate material, **not a public
quote**. There is no public projection or render endpoint in this stage. Its
representation hides content and ordinary JSON serialization is unavailable;
never use `dataclasses.asdict` or private fields in a renderer. #29 must produce
grounded privacy-safe paraphrases/evidence; #31/#32 independently gate audience
projections and discard all source refs/provenance/counts. #33 must recheck raw
expiry and withdrawal downstream. No persistence, publication or live AI is added.

`uv run pytest signal_loop/analysis/tests/test_themes.py` exercises the actual
built-in grounding validator using synthetic complete sources and #18's fake
provider, including all five categories/recurring concerns, negation, unsupported
clauses, malformed output, unknown refs, injected instructions, provider failures,
one-support restricted candidates, suppressed and empty input, and defensive
output. Full tests require a separately named disposable PostgreSQL test database
when running alongside other engineers/QA; do not reuse their test DB.

## Restricted two-week trends (#27)

`trends.compare_weeks(previous=..., current=..., at=..., reviewer=...)` implements
the deterministic, numeric, versioned [trend rules](../../_docs/trend-rules.md).
Supply two `WeeklyHistory` objects containing the original frozen #25/#26
snapshots and a trusted independent `HistoryReviewer`; no production history
reviewer is selected by default. The reviewer must attest the exact snapshot
contents, original releases, unchanged membership, safe participation and joint
inference safety without respondent joins. #33 owns wiring this fixture handoff.

`RestrictedTrends.artifact_for_analysis()` returns the defensive `trends/1.0`
candidate. `TrendUnavailable.reason` is restricted; its public status, like an
unreleased success, is always `{"status": "unavailable"}`. No endpoint or
publication is added. Unknown topic labels remain unmatched; the documented
finite alias registry is the entire matching vocabulary for this version.
Sentiment describes only positive project-win feedback, not inferred personal
mood. Workload/blocker/collaboration statements remain topic-specific. Numeric
prevalences/counts stay restricted; downstream audience gates still apply.

Run `uv run pytest signal_loop/analysis/tests/test_trends.py` for deterministic
fixture checks: inclusive directional boundaries, stable and recurring concerns,
renames, gaps, thresholds, partial withholding, source grounding, original-history
review binding, privacy failures, expiry and public-status redaction. No database,
provider call or fixture identity mapping is needed by this pure service.

## Restricted severity and evidence handoff (#28)

`severity.score_issues(eligible=..., themes=..., candidates=..., at=...,
closes_at=..., history=...)` implements the explicit weighted numeric
[severity rules](../../_docs/severity-rules.md). The result's `calculations`
contain severity, rule score, all six factors/origins and a readable explanation;
`unscored` identifies missing/uncertain factors without a severity default.
Estimates are independently checked against entire source fields; calculated
support is not a model count or roster size. Safe #27 history is required by the
integrated scorer: its current contract proves recurrence, not an isolated
appearance, so missing history yields unscored rather than zero persistence.

`SeverityAssessment.issues` is optional `RestrictedIssues`. Its
`artifact_for_analysis()` returns exact `issues/1.0`; factor metadata stays
outside canonical rows. `source_context_for_analysis()` returns defensive
`IssuesSourceContext(eligible, themes, trends, references)` for #29. The registry
contains `Reference(kind="issues", ...)` only for successfully scored canonical
rows, with project/week and earliest-source expiry. An unscored ID cannot resolve
as an issue. #29 must independently inspect source contents, grounding, counts,
privacy and joint context; neither severity nor this registry proves safety.

Inputs are trusted internal #25/#26/#27 handoffs, never client-deserialized
eligibility or publication permissions. `SeverityHistory` carries the exact
weekly snapshots and the existing history reviewer; #33 owns production wiring.
No UI, model call, dependency or storage write is added. Public status remains
uniform `unavailable`, including for critical scored candidates. The arithmetic
helper can evaluate documented theoretical factor combinations; it cannot grant
integrated eligibility or override any release gate.

Run `uv run pytest signal_loop/analysis/tests/test_severity.py` for deterministic
full-service level boundaries, factor thresholds/origins, conflicting evidence,
unknown factors, unsupported/injected estimates, unsafe urgent small-support
cases, and the exact #29 reference handoff. Tests use synthetic actual source
contents and the implemented grounding/history validators, without a live model.

## Safe evidence transformation (#29)

`evidence.transform_evidence(issues, closes_at=..., at=..., adapter=...,
context_provider=...)` accepts the actual #28 `RestrictedIssues` handoff. It calls
the #18 adapter with exact `analysis-request/1.0` inputs (complete current
feedback, themes and issues) and validates exact `evidence/1.0` output. Provider
wrappers select `EVIDENCE_INSTRUCTIONS` for this operation; source text remains
untrusted data. No vendor, production context provider or persistence is added.

The runtime uses a finite reviewed catalog, rather than treating model
`grounded=true` or referenced IDs as proof. Each item must name a scored issue
and cite at least five actual supporters of the same complete factual claim.
Every cited source is independently checked against the exact structured enum
or entire narrative field using the #26 grounder. Unknown wording, extra clauses,
negation/qualifiers, stronger certainty and unsupported facts cannot pass by
substring matching. The catalog currently covers overloaded/stretched workload,
at-risk/blocked delivery, review turnaround and handoff coordination. For example,
five `overloaded` answers support “The volume of work exceeds available capacity.”
Five complete “Review turnaround delays shared work.” answers support “Shared
work is delayed by review turnaround.” The synthetic variant “Review queues can
delay shared work.” must carry the exact label **Synthesized example from shared
feedback**. No catalog output is released when it copies an actual source passage.
All verbatim quotations are forbidden; no raw excerpt is a failure fallback.

Item grounding is separate from joint-context safety. A trusted server-side
`context_provider.load(project=..., week=...)` supplies `JointContext`: a complete
inventory of required co-accessible/current/prior scopes, their passages and
roster sizes, and ephemeral pairwise roster intersection counts. This interface
cannot accept model-generated safety flags. Scope completeness must be determined
from actual audience/access and release history by the caller, never a client or
model assertion. Current passages must exactly match all actual source narrative
fields. Every complete passage across the inventory must belong to the finite
generic grammar in `SAFE_PASSAGES`; identifying names, roles, dates, incidents,
cross-project clues and unknown prose fail closed. Nonempty contexts with fewer
than five eligible members also fail. Small known overlaps do not alone prohibit
generic statements, but they never excuse rare/identifying context. Missing
scopes/intersection facts or a changed inventory after the provider call withhold
the result. Inventory counts carry no contributor IDs or identity-to-source joins.
Only synthetic complete-inventory fixtures are supplied here; absent production
coverage withholds. This conservative stage does not establish report/audience
authorization or replace the final joint release gate in #31/#32/#33.

`EvidenceAssessment.evidence` is optional `ReleasedEvidence`. Its
`artifact_for_analysis()` returns a defensive canonical envelope containing only
accepted items. `source_context_for_analysis()` returns defensive
`EvidenceSourceContext(issues, references, joint_context)` bound to the accepted
source snapshot and inspected context. The registry contains `evidence` references
only for accepted IDs, with original scoped expiry. #30 can use the canonical
artifact alongside issues/trends while retaining raw sources locally to verify
its own rationale; this is not a serialized new schema or reusable publication
permission. Downstream decisions must check current expiry/context again.
`public_items()` exposes only `form`, `text` and the required synthesis `label`;
source IDs, issue IDs, counts, provenance and identities remain internal. A mixed
valid/unsafe response retains only independently safe items. Missing/expired
inputs, adapter failure and wholly unsafe results return uniform `unavailable`.

Run `uv run pytest signal_loop/analysis/tests/test_evidence.py` for real #28/#18
synthetic handoff, exact release text/labels, four/five/six item support, actual
source contradiction, identifying and overlapping context, context changes,
defensive snapshots, invalid output, injection and safe partial withholding.

## Grounded process recommendations (#30)

`recommendations.suggest_recommendations(assessment, evidence, closes_at=...,
at=..., adapter=..., context_provider=...)` takes #28's `SeverityAssessment` and
#29's `ReleasedEvidence`. Exact scored issues, factor metadata, trends and safe
evidence are validated against their same-scope source association. #18 receives
only canonical issues/trends/evidence in its unchanged `analysis-request/1.0`;
raw feedback remains local for independent grounding, not provider input. Factor
metadata is checked locally; it is not an invented #6/#18 schema field.

The `recommendations/1.0` candidate must include an explicit boolean
`suggest_for_team` on every row, even though #6 makes it optional generically.
The flag means a suggested option for #32/#36, never manager approval or automatic
publication. The fixed `RECOMMENDATION_INSTRUCTIONS` prompt contract belongs in
#39's eventual provider wrapper; no vendor or extra request field is introduced.
Fakes return explicit candidates; runtime gates do not trust prompt obedience.

The version-1 conservative action catalog contains practical process options:

| Supported topic | Suggested action |
| --- | --- |
| Workload overload | Review team capacity and reduce concurrent work. |
| Stretched workload | Review priorities and rebalance planned work. |
| Delivery risk | Review delivery dependencies and agree a recovery plan. |
| Delivery blocked | Review delivery blockers and agree the next unblocking step. |
| Review turnaround delay | Publish a shared review rota. |
| Handoff coordination | Agree a shared handoff checklist and coordination cadence. |

These are normative options related to the issue; sources need not have already
proposed the exact action. A recognized action for a different topic is rejected.
No employee evaluation, promotion, accusation, individual targeting or unrelated
task can pass the complete-action grammar. Unknown actions are withheld, not
loosely accepted through keyword matching. This finite catalog is deliberately
conservative, not a claim of general semantic action evaluation.

Every factual rationale must equal an accepted #29 paraphrase, or equal
`Synthesized example from shared feedback (hypothetical): ` followed by its
approved conditional synthesis. Labels and uncertainty cannot be removed to turn
an example into an asserted event. Each cited recommendation supporter must be
among that evidence item's independently grounded sources, with at least five.
The stage rechecks actual structured/source facts and #29's no-source-excerpt
invariant; provider `grounded` flags, issue severity and manager-suggestion flags
are not proof. Arbitrary causes, urgency, identities or extra clauses fail closed.

Joint privacy review is separate from grounding. The trusted context provider
must supply the exact complete #29-bound inventory of current/prior/co-access
scopes, complete passages, roster sizes and ephemeral intersection counts. Unknown
or identifying text, missing scope/pair data and invalid counts withhold before
provider work. The stage's grammar additionally recognizes the generic process
actions/labeled rationales above. The inventory is loaded again after the call;
any change requires a new decision. No participant identities or durable joins
are added. Source lifetime is rechecked using the trusted invocation time plus
real elapsed execution duration, so a late provider result cannot outlive support.

`RecommendationAssessment.recommendations` is optional `RestrictedRecommendations`.
`artifact_for_analysis()` returns the defensive exact canonical artifact, including
the restricted team flag. `source_context_for_analysis()` returns
`RecommendationSourceContext(issues, evidence, calculations, references,
joint_context)` bound to accepted content. Only accepted recommendation IDs get
scoped `Reference(kind="recommendations", ...)` records. Unsafe candidate IDs and
text are omitted, with no fallback. #31 must independently recheck every displayed
clause, dependencies, current expiry/context and combined audience safety.

`public_items()` contains only **action/rationale**, matching #6's permitted
manager recommendation fields. `suggest_for_team` stays in the internal artifact
for #32 selection; it is never an extra manager-display field. This projection is
not a publication operation: `public_status()` remains `unavailable`, even after
successful generation. No report storage, task execution, UI or email is added.

Empty/withheld/expired inputs, missing context and wholly unsafe output produce no
recommendation. Valid safe items can survive alongside unrelated rejected items;
malformed contracts and provider failures fail closed. Run
`uv run pytest signal_loop/analysis/tests/test_recommendations.py` for real #28/#29
handoffs with fake #18 calls, practical new actions, flags, synthesis, unsupported
or employee-directed text, context changes, deadline crossing, empty/no-call
behavior, provider failures and the defensive #31 canonical-reference handoff.
