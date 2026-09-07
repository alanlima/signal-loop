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
