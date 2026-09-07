# Project issue severity rules

Rule version **`severity/1.0`**, implemented by the pure
`signal_loop.analysis.severity.score_issues` service. These are #28's explicit
analysis choices, not changes to anonymity policy `1.0`. A severity score is not
an employee rating, confidence estimate, roster ranking or publication decision.

## Inputs and exact contracts

Use the trusted #25 `RestrictedAnalysisInput` and #26 `RestrictedThemes` plus
typed `IssueCandidate(id, theme, category, impact, urgency)` objects. Categories
must match the supported theme's delivery/workload/collaboration category, or
`recurring_concern` backed by recurrence. Wins are not automatically issues.
Candidate IDs are opaque project-week-local IDs, unique across source/theme/trend
references; never identity-derived keys. Synthetic fixtures may supply these
interfaces. They must still pass the real source/shape/scope/expiry checks.

Frequency/support come from independently admitted #25 sources supporting the
whole #26 claim. Runtime checks again compare theme support against actual
complete source fields or structured facts through #26's conservative grounder.
No roster value, model count, duplicate answer or follow-up increases support.

`SeverityHistory(previous, current, reviewer)` supplies #27's exact original
weekly history. Current input/theme content must equal this invocation's inputs.
The service calls the pure #27 comparison, retaining its release, consecutive
history, membership, participation and joint-inference gates. It does not accept
model/caller trend booleans instead. No provider, database or history persistence
is added; #33 still owns production wiring. Without safe temporal evidence, the
issue is explicitly unscored.

## Factor mapping and weights

| Factor | Value -> unweighted points | Weight | Origin |
| --- | --- | --- | --- |
| Frequency in eligible project feedback | <25% -> 0; >=25% and <50% -> 1; >=50% -> 2 | 1 | calculated as verified supporters / eligible contributors, exact integer arithmetic |
| Distinct contributor support | 1–4 -> 0; 5–9 -> 1; 10 or more -> 2 | 1 | calculated from #25-admitted sources after whole-claim grounding |
| Trend direction | improving -> 0; persisting -> 1; worsening -> 2 | 1 | calculated by independently safe #27 comparison |
| Persistence | verified isolated appearance -> 0; two consecutive supported appearances -> 1 | 1 | calculated historical evidence, never guessed from absent output |
| Potential impact | none -> 0; localized process -> 1; project delivery -> 2; project objective -> 3 | 2 | estimated, independently grounded against sources |
| Urgency | none -> 0; next weekly window -> 1; current weekly window -> 2; immediate -> 3 | 2 | estimated, independently grounded against sources |

Frequency describes submitted feedback, not the roster. Absolute support is a
separate capped corroboration factor, so large teams cannot increase its weight
without bound. Impact/urgency are weighted twice as strongly as each other factor;
an improving concern can still deserve attention when its impact or urgency is
high. This is a prioritization heuristic, not a calibrated forecast or confidence
probability. No numeric score/count/frequency is a reader-facing MVP output.

The weighted sum is 0–19. **Low: 0–4; moderate: 5–9; high: 10–14;
critical: 15–19.** Boundaries are inclusive, with no rounding. The arithmetic
function can represent verified isolated/small-support fixture cases; this does
not confer eligibility or bypass the production entry point's gates.

#27's present two-week contract proves recurrence, not isolated absence. Therefore
the integrated scorer currently obtains persistence=1 from safe recurrence or
returns unscored. It must never assign 0 because a prior theme is missing,
suppressed, unmatched, expired or privacy-withheld. Similarly, under-five support
does not pass #27's temporal gate even if the arithmetic function gives a high
score. Future isolated-appearance evidence needs an explicit reviewed handoff;
no implicit fallback is implemented here.

## Estimated factors and independent grounding

`Estimate(value, origin)` has origin `model_estimated` or `synthetic_estimate`.
Origin records how a value was proposed; neither origin, a model confidence nor
a model boolean proves the value. Each issue supporter must independently support
each estimate's entire canonical factual statement. The built-in runtime verifier
requires exact equality with a **complete** source note or follow-up answer:

| Input value | Canonical impact statement |
| --- | --- |
| none | `No project impact is expected.` |
| localized | `A localized project process is affected.` |
| project_delivery | `Project delivery is affected.` |
| project_objective | `The project objective is at risk.` |

| Input value | Canonical urgency statement |
| --- | --- |
| none | `No action is currently needed.` |
| next_window | `Action is needed next week.` |
| current_window | `Action is needed this week.` |
| immediate | `Action is needed immediately.` |

These temporal labels retain the source's reporting-week context; scoring does
not reinterpret them against a fresh wall clock or invent a deadline. The
service does not extract estimates or call a model; extraction remains #26's
handoff and vendor processing #39. #6 has no impact/urgency fields, so estimates
remain typed internal metadata, never invented fields in canonical theme rows.
Fixtures can provide model-estimated values without a live model.

Whole-field comparison intentionally rejects paraphrases, partial matches,
negations, qualifications and prompt-injection suffixes. A statement about only
one supporter cannot establish impact/urgency for all issue supporters. This
conservative vocabulary is documented, not a claim of general semantic
entailment. Unknown prose is insufficient evidence, never a silently assumed
zero or high-confidence estimate.

## Missing, uncertain and invalid inputs

Missing estimate or `Estimate(None, valid_origin)` means unknown. A recognized
value without full source grounding is also uncertain: that candidate receives
`Unscored(reason="insufficient_estimate_evidence")`. Missing/unsafe/gapped temporal
evidence receives `insufficient_history`. No severity or canonical issue row is
created. Invalid types (including bool-as-int), unknown enum/origin/version,
references, cross-scope content or fabricated support are rejected as
`invalid_input`; malformed/mismatched historical context is `invalid_history`.
All reasons are restricted. Other independently valid candidates may still score.

## Output and #29 handoff

`SeverityAssessment` contains `rule_version`, per-issue `Calculation` objects
(severity, score, contributing `Factor` values/points/weights/origins and readable
explanation), separate unscored results, and optional `issues: RestrictedIssues`.
`artifact_for_analysis()` returns a defensive exact **`issues/1.0`** envelope.
Each row has only id/theme/category/severity/explanation/support and optional trend.
Do not add factor metadata or rule_version to a #6 issue row.

`source_context_for_analysis()` returns defensive `IssuesSourceContext(eligible,
themes, trends, references)`. Registry records derive from actual source/theme/
trend/scored issue artifacts and scope/expiry metadata. Unscored IDs do not
resolve. #29 can resolve `Reference(kind="issues", ...)` for an actual scored
row, but must independently validate every evidence claim, support and privacy
gate. Severity, our registry and #27's flag are not evidence-publication proof.

Candidates inherit the earliest source/theme/trend expiry. Representations hide
content; public status is uniformly `unavailable`, even for critical scored
issues. No employee filters, identity joins, release endpoints or production
side effects are introduced. #29/#31/#32 remain mandatory audience gates.

## Synthetic boundary table

Sums below follow factor order frequency + support + trend + persistence +
weighted impact + weighted urgency. Sources, estimates and safe history are
explicit fixtures, never production assumptions.

| Score | Factor sum | Expected |
| --- | --- | --- |
| 4 | 0+1+0+1+2+0 | low, upper boundary |
| 5 | 1+1+0+1+2+0 | moderate, adjacent lower boundary |
| 9 | 0+1+1+1+2+4 | moderate, upper boundary |
| 10 | 1+1+1+1+2+4 | high, adjacent lower boundary |
| 14 | 1+1+1+1+4+6 | high, upper boundary |
| 15 | 2+1+1+1+4+6 | critical, adjacent lower boundary |
| 19 | 2+2+2+1+6+6 | critical, maximum |

Additional tests cover all arithmetic score boundaries including theoretical 0,
exact/below/above 25% and 50%, support 4/5/9/10, conflicting improving/urgent
factors, partial unscored batches, unknown estimates/history, synthetic
unsupported/negated/injected claims, unsafe urgent small-support cases, and the
canonical #29 reference handoff without identity or publication authority.
