# Deterministic project trend rules

Rule version `project-trends/1.0`, producer version `1.0`. This document defines
#27's numeric analysis rule; it does not change policy `1.0`, grant publication,
or introduce a new artifact schema. Output remains restricted `trends/1.0`.

## Window, minimum and available evidence

Compare exactly two weekly snapshots: the requested organisation-local Monday
and its immediately preceding Monday (seven calendar days earlier). Minimum
history is **two independently eligible, closed, unexpired, already released
weeks**. No rolling average, skipped-week comparison, interpolation, zero fill,
participant filter, individual sentiment score or persistent respondent matching
exists. A missing/suppressed week, fewer than two snapshots, expired support,
changed membership, uncertain participation safety, revised release or failed
joint inference review yields restricted unavailability. The public status is
always just `unavailable`; internal failure reasons are never reader-facing.

The history interface carries each week's #25 restricted input, #26 restricted
themes, window close and a project-week-local aggregate reference. These are
fixtures until #33 wires frozen history. A trusted server-injected history reviewer
must bind its decision to those exact complete snapshots and independently verify
both original releases, unchanged membership, safe participation/differencing and
joint inference safety. Boolean fields in input or model output are not proof.
There is no default production reviewer. Do not create a participant-set join or
identity-to-feedback map to implement it. A roster change requires two subsequent
unchanged, independently released weeks to establish a new baseline.

## Topic identity and renamed themes

Theme IDs remain week-local. Match semantic topics only through the following
finite versioned catalog, not IDs, substring similarity, fuzzy text matching,
embeddings or inferred synonyms. Both category and exact statement must match a
catalog entry. Aliases below are explicit equivalent labels; their change is a
rename, not disappearance or a new concern. Unknown labels and category changes
remain unmatched and cannot imply recovery. Expanding this registry changes the
rule version and requires review; no runtime caller-supplied alias override.

| Topic | Dimension | Category | Accepted exact statements |
| --- | --- | --- | --- |
| shared-milestone | sentiment | wins | `The team completed the shared milestone.`; `The shared milestone was completed by the team.` |
| workload-overload | workload | workload | `Workload is overloaded.` |
| delivery-blocked | blocker | delivery | `Delivery is blocked.` |
| review-delay | blocker | delivery | `Review turnaround delays shared work.`; `Shared work is delayed by review turnaround.` |
| handoff-coordination | collaboration | collaboration | `Teams have trouble coordinating handoffs.`; `Handoffs are difficult to coordinate between teams.` |

Here **sentiment means prevalence of positive project-win feedback**, not personal
mood, health or employee scoring. Workload/blocker/collaboration refer only to the
specified grounded concern. Do not generalize a single topic's movement to every
aspect of that dimension. Every generated statement names the topic.
This definition uses #6/#26's grounded `wins` category as the available favorable
project signal; those contracts contain no general sentiment scalar or personal
mood field. It measures explicit positive project outcomes. It does **not** infer
negative feelings from an absent win, classify unrecognized prose, or describe
overall morale. A decline means only that this specific positive feedback became
less prevalent among eligible contributions. This restricted operational
definition and its finite vocabulary must be assessed explicitly in #27 QA;
broader semantic sentiment inference is not claimed by this implementation.

Only one theme per topic per snapshot is accepted; duplicate aliases for the same
topic are ambiguous and reject the comparison rather than double-count support.
Each matched theme must have at least **five verified distinct supporting
contributors in each week**. Source IDs are unique only within their own week.
The #25 admission invariant plus #26 whole-claim grounding establish support;
neither roster size nor model `distinct_support` alone does so. Missing or
below-threshold topics are withheld individually; if none remain, unavailable.

## Numeric comparison and recurrence

For each matched topic, restricted prevalence is `verified theme supporters /
eligible contributors` in that week. This is prevalence in submitted project
feedback, never an estimate of the entire roster. Values, counts, percentages and
numeric deltas are never public output. Calculate changes with integer cross
multiplication, with no floating-point rounding.

The minimum directional change is **10 percentage points**, inclusive. For a
concern, an increase of at least 10 points is `worsening`; a decrease of at least
10 points is `improving` (recovering). For the positive-win sentiment topic, those
directions are reversed. An absolute difference below 10 points is `persisting`
(stable prevalence), even if nonzero. At exactly 10 points, direction applies.

Independently, every matched **concern** with five supporters in both consecutive
weeks produces a recurrence row with direction `persisting`, including when its
prevalence worsens or recovers. This means two supported consecutive appearances,
not a longer historical claim. Positive wins do not become recurring concerns.
The `trends/1.0` enum has no `recovering`, `stable`, `recurring` or `renamed` values:
use the directions above and fixed qualitative topic-specific statements. Rename
does not add an invented schema field; output refers to the current theme ID.

Rows are ordered by catalog topic, movement before recurrence, with deterministic
project-week-local IDs `trend_1`, `trend_2`, etc. No source ID is used as a
cross-week key. Permitted provenance refers only to current themes and the
previous scoped aggregate; previous raw source IDs are not copied into output.
Expiry is no later than either input/theme/source lifetime. Unknown schema/policy
versions reject. Identical snapshots, decision and rule version produce identical
output; there are no model calls, randomness, writes or wall-clock reads.

## Worked synthetic boundaries

All cases have two consecutive released weeks, grounded sources, unchanged
membership and independently safe joint review unless stated. Counts are test
inputs only. Each support ratio is `support / eligible contributors`.

| Case | Prior -> current | Expected |
| --- | --- | --- |
| workload worsening | 5/10 -> 6/10 | worsening at +10 points; recurrence |
| blocker recovering | 6/10 -> 5/10 | improving at -10 points; recurrence |
| collaboration stable | 5/10 -> 5/10 | persisting; recurrence |
| just below threshold | 5/20 -> 6/20 | persisting at +5 points; recurrence |
| exact threshold, different denominator | 5/10 -> 9/15 | worsening at +10 points; recurrence, only with affirmative participation safety |
| positive sentiment | 5/10 -> 6/10 | improving, no concern recurrence |
| renamed review delay | alias 1 at 5/10 -> alias 2 at 5/10 | same topic, persisting and recurrence, current theme reference |
| support boundary | 4/10 -> 5/10 | unavailable topic; no fabricated recovery |
| threshold plus one | 6/10 -> 6/10 | persisting; recurrence |
| isolated concern | no matched prior theme -> 5/10 | unavailable topic; no fabricated zero baseline |
| gap | W1 and W3, or suppressed W2 | unavailable; never across-gap improvement |
| membership change | 5/10 -> 6/10, member joins/leaves | unavailable, despite eligible weeks |
| known new respondent explains change | 5/10 -> 6/11 | unavailable when participation review unsafe/unknown |
| revised/withdrawn/expired release | otherwise valid pair | unavailable; no refreshed comparison |

The fixture reviewer supplies explicit independent synthetic history evidence.
#33 owns production release-history and safety wiring; #29/#31/#32 still own
final semantic/privacy/audience gates. Restricted trend candidates cannot be
serialized directly to a renderer or treated as publication permission.
