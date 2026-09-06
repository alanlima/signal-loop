# Analysis and release contracts

Contract family `1.0`, policy versions `1.0`, decided 2026-09-07. These specifications bind future implementations to [anonymity](anonymity-policy.md) and [check-in](check-in-policy.md) policy. They do not authorize collection or publication before the linked enforcement blockers clear.

## 1. Common envelope, validation and trust

Every full artifact has required fields `schema` (the exact kind/version string specified below), `project` (opaque project ID string, 1-64 ASCII letters/digits/underscore/hyphen), `week` (organisation-local Monday date `YYYY-MM-DD`, per the #12 timezone decision), `privacy_policy` (exact supported version string, here `1.0`), and `data` (the kind's object). No additional fields are allowed at any level unless listed. Optional means absent, never null. Strings are plain text, normalized LF, length measured in Unicode code points. Empty strings are invalid except expressly optional questionnaire text. IDs are 1-64 characters in the project-ID alphabet. Arrays have unique IDs, and references must resolve within their declared project/week except an expressly scoped prior-week aggregate reference.

Schema validation rejects unknown fields, bad types, wrong enums, unsupported versions, invalid dates, duplicate IDs, unresolved/cross-project references and exceeded limits before processing. Validate structure/enums first, local invariants (including consecutive weeks and duplicate references) second, reference resolution third, then grounding and privacy. This ordering defines the expected first rejection in examples with multiple defects. Semantic validation separately verifies grounding, support and publication safety. An AI-produced boolean/count is an untrusted claim, never proof. `invalid_contract` is a restricted error code; readers only see generic availability. All feedback-related artifacts below are restricted unless explicitly designated as projections. Never serialize them straight to a view.

Every raw/restricted artifact also has required envelope `expires_at` (UTC RFC3339 time) and `provenance` (object: required `producer` ID, `producer_version` 1-32-character string, `input_refs` array of 0-100 opaque artifact IDs). `expires_at` cannot exceed 14 days after week closure or the earliest source expiry; questionnaire intake uses submission policy expiry. No identity, shared cross-project journey ID, credential, IP or fine-grained submission timestamp is permitted. Provenance IDs are random scope-local references, not hashes of user identifiers/content. They expire with the raw source. Final releases discard raw provenance and retain only safe release-ledger metadata allowed by #4.

Examples below are **complete `data` values** for each contract, paired with the common envelope fixture E below. Thus `E(schema, data)` is the complete valid or invalid artifact; no unspecified fields/defaults are required. This explicit fixture composition avoids repeating identical context eight times and is the input format downstream tests must assemble. Invalid examples each change only the illustrated condition in an otherwise valid context.

```json
{"schema":"REPLACE_WITH_KIND/1.0","project":"cedar","week":"2026-09-07","privacy_policy":"1.0","expires_at":"2026-09-21T00:00:00Z","provenance":{"producer":"fixture","producer_version":"1.0","input_refs":[]},"data":{}}
```

Synthetic fixture registry: Cedar week 2026-09-07 is closed at 2026-09-14T00:00:00Z. `s1` through `s5` are five accepted, independently admitted substantive submissions supporting ordinary review delays, with no identifying content. Their within-project-week distinctness proof is valid. `a1` is the current approved restricted aggregate, `a0` the preceding week 2026-08-31 aggregate with five supporters, unchanged roster and passed joint inference review. IDs `t1`, `tr1`, `i1`, `e1`, `r1` resolve to the valid artifacts below. This registry is synthetic test context, never an identity map or permission to trust client-supplied counts.

## 2. Project-week feedback: `feedback/1.0`

Restricted input/output of anonymous persistence. Required `source` ID, `delivery` enum `on_track|at_risk|blocked|not_enough_context|prefer_not_to_say`, `workload` enum `manageable|stretched|overloaded|not_enough_context|prefer_not_to_say`. Optional `note` text 0-320, `follow_up` object with required `question` enum `F1|F2` and `answer` text 0-240. No personal P1-P5 fields. Only substantive sections are admitted; unknown/declined values and blank text supply no claim support. Follow-up ID must be eligible under #5 and backed by its draft budget validation; persistence must not preserve draft metadata. One source reference per admitted project-week contribution, retries cannot mint another.

Valid E(feedback/1.0, data):
```json
{"source":"s1","delivery":"at_risk","workload":"manageable","note":"Review turnaround delays shared work."}
```
Invalid: forbidden personal narrative. Reject `unknown_field` before persistence.
```json
{"source":"s1","delivery":"at_risk","workload":"manageable","personal_challenges":"I was the only overnight specialist."}
```

## 3. Themes: `themes/1.0`

Restricted analysis output. Required `items` array 0-50 of objects: `id` ID, `statement` text 1-500, `support` array 1-10000 distinct source refs, `distinct_support` integer 1-10000. Count must equal independently verified distinct supporters, not array length guessed by a provider. Optional `category` enum `delivery|workload|collaboration|wins|support`. Themes below five may exist only as restricted intermediate candidates; publishing any theme requires the release gate. Empty array is valid and cannot by itself become an available report.

Valid:
```json
{"items":[{"id":"t1","statement":"Review turnaround delays shared work.","category":"delivery","support":["s1","s2","s3","s4","s5"],"distinct_support":5}]}
```
Invalid: duplicate support and fabricated count; reject `duplicate_reference` and never infer five people from repeated answers.
```json
{"items":[{"id":"t1","statement":"Review delays.","support":["s1","s1","s1","s1","s1"],"distinct_support":5}]}
```

## 4. Trends: `trends/1.0`

Required `items` array 0-50, each `id`, `theme` current theme ID, `previous_week` Monday date, `previous_aggregate` opaque aggregate ID, `direction` enum `persisting|improving|worsening`, `statement` text 1-500, `current_support` and `previous_support` integers >=5, and `comparison_safe` boolean. A candidate with false safety must be withheld, not projected. Previous week must be immediately consecutive; both independently eligible, roster unchanged and joint review passed before a ready output. No participant cohort IDs, response-count deltas or numerical trends are public. Optional fields: none.

Valid:
```json
{"items":[{"id":"tr1","theme":"t1","previous_week":"2026-08-31","previous_aggregate":"a0","direction":"persisting","statement":"Review delays persist.","current_support":5,"previous_support":5,"comparison_safe":true}]}
```
Invalid: a gap cannot mean improvement; reject `nonconsecutive_window` even if a matching older aggregate exists.
```json
{"items":[{"id":"tr1","theme":"t1","previous_week":"2026-08-24","previous_aggregate":"a_older","direction":"improving","statement":"Things improved across the missing week.","current_support":5,"previous_support":5,"comparison_safe":true}]}
```

## 5. Issues/severity: `issues/1.0`

Required `items` array 0-50; each `id`, `theme` ID, `category` enum `delivery|workload|collaboration|recurring_concern`, `severity` enum `low|moderate|high|critical`, `explanation` text 1-800, `support` array 1-10000 unique source refs. Optional `trend` ID. References must ground every factual clause; severity is assessed by #28, cannot override privacy. Numeric scoring formula remains #28 ownership; this contract fixes output representation, not that formula. Candidate artifacts may include insufficient support, but release must remove dependent issues/recommendations.

Valid:
```json
{"items":[{"id":"i1","theme":"t1","category":"delivery","severity":"moderate","explanation":"Shared review delays affect delivery.","support":["s1","s2","s3","s4","s5"],"trend":"tr1"}]}
```
Invalid: unknown severity; reject `invalid_enum`.
```json
{"items":[{"id":"i1","theme":"t1","category":"delivery","severity":"urgent","explanation":"Review delays.","support":["s1"]}]}
```

## 6. Evidence: `evidence/1.0`

Required `items` array 0-100; each `id`, `issue` ID, `form` enum `paraphrase|synthesis`, `text` 1-800, `support` array 5-10000 unique source refs, `grounded` boolean. Optional `label` text; required and exactly `Synthesized example from shared feedback` when form=synthesis, absent for paraphrase. Grounded=false cannot be ready/released. Each factual component needs five actual supporters; blending five unrelated unique incidents is invalid. No verbatim quotes, even with names removed.

Valid:
```json
{"items":[{"id":"e1","issue":"i1","form":"paraphrase","text":"Review turnaround delays shared work.","support":["s1","s2","s3","s4","s5"],"grounded":true}]}
```
Invalid: verbatim form forbidden; reject `invalid_enum`.
```json
{"items":[{"id":"e1","issue":"i1","form":"quote","text":"I waited for review.","support":["s1","s2","s3","s4","s5"],"grounded":true}]}
```

## 7. Recommendations: `recommendations/1.0`

Required `items` array 0-50; each `id`, `issue` ID, `action` 1-500, `rationale` 1-800, `support` array 5-10000 unique source refs. Optional `suggest_for_team` boolean (absence means false, never permission to publish). Action must not target an identifiable contributor; factual rationale must be grounded and meet item gates. Manager approval/team suggestion never bypasses review. Edited commitments use the safe action projection described in section 9 and re-enter privacy review.

Valid:
```json
{"items":[{"id":"r1","issue":"i1","action":"Publish a shared review rota.","rationale":"Shared review delays affect delivery.","support":["s1","s2","s3","s4","s5"],"suggest_for_team":true}]}
```
Invalid: source from Birch in Cedar scope; reject `cross_scope_reference`.
```json
{"items":[{"id":"r1","issue":"i1","action":"Publish a shared rota.","rationale":"Shared delays.","support":["s1","s2","s3","s4","birch_s5"]}]}
```

## 8. Manager reports: `manager-report/1.0`

Restricted pre-release composition. Required `title` text 1-120, `overview` text 1-800, `themes` array 0-50 theme IDs, `issues` array 0-50 issue IDs, `evidence` array 0-100 evidence IDs, `recommendations` array 0-50 recommendation IDs, `trends` array 0-50 trend IDs. Optional fields: none. Every reference must resolve to a same-scope permitted artifact; narrative overview is also a factual item requiring grounding/gates in release control. Report must retain at least one safe substantive item to publish; referenced unsafe artifacts and dependent overview clauses are removed before release. References never reach the manager.

Valid:
```json
{"title":"Cedar weekly review","overview":"Review turnaround delays shared work.","themes":["t1"],"issues":["i1"],"evidence":["e1"],"recommendations":["r1"],"trends":["tr1"]}
```
Invalid: attempted raw feedback export; reject `unknown_field`.
```json
{"title":"Cedar weekly review","overview":"Review delays.","themes":["t1"],"issues":[],"evidence":[],"recommendations":[],"trends":[],"raw_feedback":["s1"]}
```

## 9. Team summaries: `team-summary/1.0`

Restricted pre-release composition. Required `title` text 1-120, `overview` text 1-800, `themes` array 0-50 theme IDs, `next_week_focus` array 0-10 text strings 1-500, `commitments` array 0-10 objects with `text` 1-500 and `approved` boolean. Optional `trends` array 0-50 trend IDs. Unapproved commitment candidates remain restricted and are never projected; manager approval is necessary but not sufficient. Factual focus/commitment wording needs grounding; generic actions without private factual claims still require context review. No manager-only severity/evidence fields accepted. Jointly compare both audience candidates so their difference cannot reveal suppressed facts.

Valid:
```json
{"title":"Cedar weekly summary","overview":"Review turnaround delays shared work.","themes":["t1"],"next_week_focus":["Improve shared review turnaround."],"commitments":[{"text":"Publish a shared review rota.","approved":true}],"trends":["tr1"]}
```
Invalid: manager-only explanation in team contract; reject `unknown_field`.
```json
{"title":"Cedar weekly summary","overview":"Review delays.","themes":["t1"],"next_week_focus":[],"commitments":[],"manager_severity_explanation":"Critical concern from a distinctive incident."}
```

## 10. Release control and audience projections

`release-control/1.0` is restricted, never renderer input. It uses E and required data: `audience` enum team|manager; `state` enum pending|running|suppressed|failed|ready; `distinct_contributors` integer 0-10000 or absent if not yet verified; `count_verified` boolean; `items` array of gate objects (`ref` ID, `support` integer >=0 if known, `grounded` boolean, `content_safe` boolean, `inference_safe` boolean, `decision` enum allow|withhold); `report_eligible` boolean; `joint_audience_safe` boolean; `reason_codes` array of enums count_unknown|too_few|unsafe_content|unsafe_inference|no_safe_items|processing_error. Optional `error_code` content-free enum invalid_contract|provider_failed|expired_source|lease_expired. Although count can be absent, all booleans are required and default to false at creation. Neither provider nor manager writes these decisions directly; analysis verifies and reporting owns final transition. All factual overview/focus/commitment clauses have gate refs too. False/unknown checks fail closed. Provenance, counts and suppression reasons remain restricted and expire with raw source material.

Valid data in the fixture context (gate t1 represents the only projected theme):
```json
{"audience":"team","state":"ready","distinct_contributors":5,"count_verified":true,"items":[{"ref":"t1","support":5,"grounded":true,"content_safe":true,"inference_safe":true,"decision":"allow"}],"report_eligible":true,"joint_audience_safe":true,"reason_codes":[]}
```
Invalid (ready with count uncertainty):
```json
{"audience":"team","state":"ready","count_verified":false,"items":[],"report_eligible":false,"joint_audience_safe":false,"reason_codes":["count_unknown"]}
```
Reject `invalid_ready_transition`. Ready requires independently verified count >=5, every released factual item support >=5 and all safety gates true, at least one safe item, correct audience authorization and joint review. Suppress individual failed items/dependents; if none remain suppress entire report. High severity/approval never overrides this.

Public means an **authorized product audience**, not public internet. `audience-release/1.0` deliberately does NOT use E: required `schema`, `project`, `week`, `audience` team|manager, `status` available|unavailable|not_yet_available. Only available permits/requires `content`: `title` 1-120, `overview` 1-800, `themes` array of safe text 1-500, `trends` array of safe qualitative text 1-500. Manager content additionally requires `issues` array of {severity, explanation}, `evidence` array of {form,text,optional label}, `recommendations` array of {action,rationale}, using enums/limits above. Team content additionally requires `next_week_focus` and `commitments` arrays of safe text 1-500. Arrays retain maxima from their restricted contracts. No other fields, count hints, source IDs, raw provenance, suppressed-item placeholders, error details or policy badges. A separate internal immutable ledger retains policy version, release identity and state, not raw references. Unavailable payloads contain no content and represent every suppression/failure/missing/withdrawal reason identically. Not_yet_available depends only on the public schedule.

Valid complete team projection:
```json
{"schema":"audience-release/1.0","project":"cedar","week":"2026-09-07","audience":"team","status":"available","content":{"title":"Cedar weekly summary","overview":"Review turnaround delays shared work.","themes":["Review delays affect delivery."],"trends":[],"next_week_focus":["Improve review turnaround."],"commitments":["Publish a shared review rota."]}}
```
Invalid complete projection: reject `unknown_field` rather than leaking suppressed participation.
```json
{"schema":"audience-release/1.0","project":"cedar","week":"2026-09-07","audience":"team","status":"unavailable","distinct_contributors":4}
```

## 11. State machine, keys and idempotency

Pipeline owns key `(project, week, artifact kind, schema version, privacy policy version, producer version)` and a scoped opaque work ID, never a participant/journey ID. A retry for that key reuses the same logical artifact; source refs, leases and gate records stay restricted. Atomic compare-and-set leases prevent concurrent workers from publishing two results. Provider nondeterminism cannot overwrite a ready release. A changed producer version is a new internal candidate key, not permission for another audience release.

| Transition | Owner and condition | Reader visibility |
| --- | --- | --- |
| absent -> pending | pipeline creates scoped work after window closure | Unavailable, or schedule-only not_yet_available before closure |
| pending -> running | pipeline grants bounded lease | Unavailable |
| running -> failed | schema/provider/expiry/internal failure | Unavailable; restricted content-free error code only |
| failed -> pending | pipeline retry, same key, within raw expiry and 24-hour task TTL | Unavailable; never reset data expiry |
| running -> suppressed | verified privacy failure/unknown safety/no safe items | Unavailable, no public reason |
| running -> ready | reporting verifies full gate, atomically creates first immutable audience release | Approved safe projection only |
| suppressed -> pending | explicit pipeline retry before any release, e.g. transient check restored, within expiry | Unavailable; numeric/privacy rules unchanged |
| ready -> suppressed | reporting withdraws unsafe existing content/dependents | Remaining independently safe original content or uniform unavailable; no replacement/new text |

No ready -> running revision in MVP. No late sixth response refresh. Unique release constraint is `(project, week, audience)` across all versions; first release is immutable except withdrawal. A publication ledger survives raw expiry with safe release for at most 365 days from publication. Pending/failed/suppressed raw artifacts expire under #4, retries/dead letters after 24 hours from task creation, without extending source lifetime. Historic comparisons require consecutive safe aggregates available within retention; no reconstruction of expired raw sources or missing-week interpolation.

Schema/policy version mismatch fails closed as `invalid_contract`; never coerce unsupported major/minor versions or silently drop unknown fields. A future migration requires explicit reviewed adapter, fixtures, privacy review and version registration. It cannot relax existing release constraints. Stored supported old projections remain readable until normal expiry/withdrawal, not regenerated under a new policy.

## 12. Fake boundaries and resolved conflicts

Until implementations exist, #18 supplies a deterministic fake provider returning selected valid/invalid fixture artifacts from this document for a named test case. Fixed input -> fixed output; no credentials/network/email. Fixtures are validated by the same contracts and gates as real providers. A fixture's synthetic support registry is explicit test input, not an implementation shortcut for real distinctness. Missing real count/grounding evidence must suppress output, never assume the fixture's five supporters. #33 owns retry/state fixtures including timeout, malformed response, duplicate work and withdrawal; #40 turns invalid examples and policy scenarios into regression checks after reading testing guidelines.

Resolved policy tensions: source refs enable only project-week grounding and cannot identify participants or span projects; privacy version/counts/provenance belong solely to restricted control, while safe ledger retains only version/release state after raw expiry; themes may contain unsafe restricted candidates but evidence/release gates cannot expose them; #5 personal fields never enter analysis; recommendations and manager approval do not bypass suppression; historical support cannot create durable respondent joins. #13 must prove distinctness/admission without identity mapping; #38 enforces lifetimes/logging; #39 verifies provider requirements; #42 proves operational separation. Until these clear, contracts are specifications and production release remains blocked.

Self-review for #6: module ownership/directions in architecture; all eight requested contract kinds with fields/types/validation and valid/invalid JSON in sections 2-9; restricted/public split in 1/10; states in 11; keys/retries/version handling/fakes in 11-12; resolved policy/provenance boundaries in 10/12. Documentation only, no application code or dependencies.
