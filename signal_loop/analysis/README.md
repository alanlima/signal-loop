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
contract. #18 continues to use its existing `analysis-request/1.0` inputs; #33
must build and validate that request and scoped reference registry from these
canonical artifacts. #18 accepts at most 100 artifacts per request; larger input
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
