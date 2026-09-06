# MVP anonymity and publication policy

Version: 1.0. Decision date: 2026-09-07. Status: policy decided; release blocked until the enforcement evidence below exists. Owner: product policy; implementation owners are the linked issues. All examples are synthetic.

This policy governs every project-week output in every delivery channel, including HTML, HTMX fragments, APIs, exports, caches, notifications, and generated text. It is mandatory and has no manager or administrator override. A future policy change needs a new reviewed version; existing published material must be included in its inference review.

## 1. Guarantee and threat model

The product must prevent team members, managers, and application administrators from retrieving raw submitted feedback or linking released feedback to a contributor through product-provided identifiers, joins, counts, or unsafe content. Publication fails closed when this cannot be demonstrated. We do not promise mathematical anonymity against arbitrary prior knowledge, collusion, a contributor voluntarily identifying themselves, or privileged infrastructure compromise. Five contributors and removing names do not prove anonymity.

Assume readers know project rosters, job roles, leave schedules and incidents; compare team and manager versions; belong to several projects; retain old reports; and may share screenshots. Assume a manager may know what four people said. Where such plausible knowledge isolates the remaining source, withhold the affected material even at the threshold. Do not claim that lack of a known attack proves safety. Severe feedback has no emergency publication bypass in this product; SignalLoop is not an emergency reporting channel.

Application authorization and operator power are different. An infrastructure operator may technically read databases, memory or backups. Encryption at rest does not protect against every live operator. Minimize access, separate duties, require time-limited audited access and independent approval, and prohibit routine content browsing. A manager who also operates infrastructure retains that technical risk: no manager-side privilege grants it, and that deployment cannot claim the normal role separation. Release requires an independent operator/access arrangement or withholding feedback collection until it exists ([#42](https://github.com/alanlima/signal-loop/issues/42)).

## 2. Fixed decision table

All values below are policy v1.0 and fixed for the MVP.

| Rule | Value and decision | Rationale / output |
| --- | --- | --- |
| P1 report eligibility | At least 5 distinct contributors in the closed project-week | Below 5, unknown count, or invalid counting proof: withhold the entire report for both audiences. Roster size is not a count. |
| P2 item eligibility | At least 5 distinct supporting contributors for each theme, evidence statement, metric and derived factual claim | Same threshold as the report; count only actual support. Below 5 or uncertain: remove the item and every dependent explanation/recommendation. |
| P3 publication window | ISO week Monday 00:00:00 UTC inclusive to the following Monday exclusive; close once at that boundary | No live reports, rolling-window counts, or late additions. A submission at the boundary belongs to the next open week. |
| P4 safe expression | No verbatim feedback quotes; only privacy-reviewed paraphrases and grounded, labelled synthesis | Names, exact dates, distinctive roles/incidents and linguistic fingerprints can identify someone. |
| P5 count disclosure | No submitted/support counts, percentages, response rates, nonrespondent lists, count buckets or numerical changes in participation to product readers | Even a threshold badge or count range permits subtraction. Internal gate counts are not report fields. |
| P6 one release | At most one immutable content release per project-week per audience; evaluate both audiences jointly before publication | No refresh after another response; no backfill or replacement releases in MVP. A correction may only withdraw existing content. |
| P7 history | Compare only consecutive, released, privacy-safe weeks with unchanged project membership, each independently passing P1/P2, and a passed joint inference review | No respondent cohort joining; uncertain comparability means no comparison. Suppressed/missing weeks break trends. |
| P8 uncertainty | Fail closed at the smallest independently safe unit; withhold whole report if its eligibility/context is unsafe | Passing counts never overrides content, access or inference checks. No safe remaining items means no report. |
| P9 releases and decisions | Same privacy gates for all audiences and all derived outputs; no severity/approval exemption | A recommendation or commitment can reveal a suppressed source as readily as evidence. |
| P10 retention | Maximum lifetimes in section 7, never extended by retries or edits | Minimize exposure and correlation; expiry applies to copies and derived source material. |

A distinct contributor means one eligible natural person submitting to one project during one week. Multiple accounts must not allow that person to inflate the count. Every accepted submission and supporting claim must have a reliable within-project-week distinctness guarantee; if it is unavailable, P1/P2 fail. Issue [#13](https://github.com/alanlima/signal-loop/issues/13) owns the admission/storage protocol and its feasibility proof. This document does not prescribe identity-bearing feedback keys, tokens, hashes, or storage joins. It forbids solving counting through a persistent identity-to-feedback map or reusable identifier across projects/weeks.

A contributor may support several themes, once per theme; that does not combine support across themes. Five different people each discussing a different topic do not establish support of five for any one topic. Withdrawn, rejected or incomplete submissions do not count. At closure freeze eligible inputs; a later privacy withdrawal can retract material but cannot produce an updated count or replacement report.

Example: synthetic person Rowan answers six prompts, three follow-ups and two project sections for Cedar in week W, with a retried submission. Cedar/W count increases by one, and each supported theme by at most one. Rowan's separate contribution to Birch/W counts once there, never as another Cedar contributor. A roster of 40 with four respondents has count four.

## 3. Publication sequence and availability

1. Verify access, closed window, policy version and trustworthy distinctness proof. Freeze the candidate release set across team and manager outputs.
2. Apply P1. If it fails, do not compose a reader-visible report from partial inputs.
3. Apply P2 separately to each factual claim, including facts behind metrics, severity, recommendations and examples. No averaging or total can smuggle in a suppressed subgroup; complementary categories that reveal a small remainder are withheld together.
4. Remove identifiers and unsafe detail, then review the transformed meaning for inference using roster context, overlapping projects, current candidate releases and previously released material. Re-run grounding and support checks after transformation. Generalization cannot turn one source into five.
5. Evaluate historical/cross-audience differences. An AI confidence score or manager review alone is not proof. Unknown safety or failure of any required review means withhold; if remaining items independently pass, publish those only. Do not show empty headings or redaction placeholders for removed items.
6. Publish once, with policy version recorded internally. No safe items means the report is unavailable. A later discovered privacy defect withdraws affected content and dependent outputs; do not replace it in the same week. Previously downloaded copies cannot be recalled, so record the incident without duplicating the content.

Readers may see the project name, week and the uniform status `Report unavailable` or an available safe report. Unavailable uses identical wording for no responses, low counts, unsafe content, processing failure, missing data and withdrawn reports; do not reveal a suppression reason, counts, number of removed items, raw errors or progress linked to individual submissions. Show no theme-level suppression indicators. The pre-closure state is `Report not yet available` based only on the public schedule. Availability inevitably signals that some policy conditions passed; do not expose which conditions or exact participation. Roster administration remains possible but must never be annotated with submission status.

## 4. Audience and access matrix

Project scope and least privilege apply even to safe outputs. Service credentials never inherit a human role. A contributor can view/edit their own draft before submission; no submitted raw-feedback retrieval is exposed, including to the author. Participation status is limited to the person's own admission flow and must not be navigable to source content.

| Data | Team member | Project manager | Org/application administrator | Infrastructure operator | Automated services |
| --- | --- | --- | --- | --- | --- |
| Raw submitted feedback / analysis inputs | No | No | No | No routine access; technically possible under controlled incident access | Only scoped intake/analysis workers for assigned purpose and lifetime |
| Draft | Own draft only | Own draft only | No privileged access | Same controlled technical-risk boundary | Draft service only; analysis when explicitly needed for that draft |
| Participation/admission records | Own minimal status only | Own minimal status only; no roster response list | No response status privileges | Controlled incident access only | Admission service only; analysis/report services cannot join identity |
| Contributor/source metadata | No | No | No | Controlled technical access; no correlation allowed | Identity only in admission; project-week source references only in analysis; no identity/content joins |
| Safe project aggregates | Own projects, only team-approved fields | Managed projects | No role-based content access; separate project role required | No routine content access | Scoped release/composition services |
| Manager reports/evidence | No | Managed projects after independent gates | No role-based access | No routine access | Scoped manager-output processing |
| Team summaries/commitments | Own projects | Managed projects after team gates | Separate project role required | No routine access | Scoped team-output processing |
| Operational diagnostics | Generic availability only | Generic availability only | Content-free health/configuration signals | Redacted operational signals and audited incident tooling | Minimal status/error codes and expiry metadata |

A person with several application roles gets only their union of allowed safe-output scopes, never raw access. Infrastructure access is not included in that union. Authentication logs, admission data and content stores must have separate access boundaries; incident reviewers must not correlate them to find authors. Any necessary incident procedure that cannot avoid such correlation blocks deployment until [#42](https://github.com/alanlima/signal-loop/issues/42) resolves it.

## 5. Content and cross-project rules

Verbatim quotes, even anonymous or short, are forbidden. Paraphrases must express shared, supported meaning using ordinary wording, omit identifying detail and retain the original uncertainty. A synthesized example is labelled `Synthesized example from shared feedback`; every factual component must be grounded in at least five supporters of that shared claim. Do not combine unique fragments from different people into a fictional event, invent dialogue or present a composite as something that happened. If grounding cannot be retained after privacy transformations, omit the example; a broad safe theme may remain.

For example, replace five independent accounts of ordinary review delays with `Review turnaround is blocking progress` if context is safe. Do not publish `Morgan, the sole overnight DBA, fixed Tuesday's outage`, or the nameless `The overnight specialist fixed the 03 September outage`. Exact dates, titles and distinctive incidents remain identifying. Generalize to a supported recurring process issue only if five sources support that generalized claim and no plausible context singles someone out; otherwise withhold it.

Cross-project review must consider co-access and roster intersections without persisting an identity-to-feedback map. [#5](https://github.com/alanlima/signal-loop/issues/5) must not fan out a personal narrative to all a person's projects or publish individual personal scores. Routing of personal context must avoid replicated identifying narratives; unresolved safe routing means do not include it in project outputs. [#13](https://github.com/alanlima/signal-loop/issues/13) must avoid cross-project/week correlation keys, identity joins, or admission identifiers in analysis references. Scoped ephemeral content comparison and membership intersection checks can identify an unsafe release combination without attributing feedback to a person; if a safe review cannot be performed within these constraints, suppress the potentially overlapping content.

Synthetic example: Cedar and Birch each have five contributors, but Rowan is their only shared member. Matching accounts of a rare accessibility incident in both reports would identify Rowan. Suppress that narrative in both candidate outputs; if one is already public, withhold the matching new item. Generic independently supported review-delay themes may still pass after removing the unique incident and reviewing the combined releases. A repeated first-person story about a unique conference trip remains unsafe even where project rosters overlap by six people: external knowledge can isolate the traveller. Neither case authorizes a durable attribution map.

## 6. Historical and derived outputs

Project-week inputs and report snapshots are immutable after closure/publication. A sixth late respondent cannot produce a refreshed five-to-six comparison, revised score, new support badge or recomputed report. Do not compare participant sets using identifiers. Stable membership is necessary but insufficient: if known attendance or response information makes one new respondent explain a change, withhold the comparison. Uncertain cohort safety also means withhold trends, while independently safe weekly themes may remain.

A project gaining or losing one member breaks trend continuity even when both weeks have five contributors. Two consecutive weeks with the new unchanged membership may become a new comparison baseline only after both pass all gates. A missing/suppressed week breaks continuity: never interpolate it as zero risk, zero workload or improvement, and do not compare across the gap. Retained earlier safe reports may remain visible if still safe; their coexistence is part of review. Numerical counts/percentages and score deltas are not reader-facing MVP outputs. A qualitative trend such as `Review delays persist` requires five independent supporters of that claim in each compared week plus joint inference safety; failure withholds that trend.

Manager-only severity explanations and recommendations cannot cite, hint at or target the source of withheld material. High severity cannot promote a four-person theme. Team summaries are separately composed and checked, not automatic redactions of manager reports. A manager-edited commitment such as `Give our only new hire support after their complaint` fails; manager approval cannot release it. A generic action such as `Publish a shared review rota` may be published if it contains no private factual assertion and passes context review; any claimed rationale must independently meet P2. Compare team and manager outputs together so their difference does not expose suppressed facts.

## 7. Raw-data handling and expiry

These are maximum lifetimes, including replicas and caches. Delete earlier when no longer needed. All durations are elapsed UTC, not business days. Deletion must propagate to active copies within 24 hours of the stated deadline; records must become inaccessible at the deadline. Failures quarantine access and alert with content-free identifiers. No manager, administrator, retry, task rerun or edit can extend a deadline. Privacy withdrawals accelerate relevant deletion/withdrawal; no content is retained for analytics, model training or debugging.

| Material | Permitted purpose / access | Expiry and starting point | Forbidden logging/correlation |
| --- | --- | --- | --- |
| Drafts | Own editing and scoped adaptive follow-up service | Earlier of submission, project-week closure, or 7 days after creation | No draft text in logs, analytics, crash reports or admin screens; no draft ID carried into published evidence |
| Submitted feedback | Scoped aggregation and privacy review only | 14 days after project-week closure | No identity, email, IP, account, admission credential or fine-grained request timestamp in feedback record; no search by person |
| Admission/participation | Eligibility and single-person counting guarantee, admission service only | 7 days after project-week closure | No source/content references; no export of respondent/nonrespondent lists; no cross-week/project tracking keys exposed to analysis |
| Analysis inputs and source references | Grounding/deduplication/privacy checks for one project-week | Earlier of source expiry or 14 days after closure; temporary provider inputs follow stricter rule below | No stable person IDs, identity joins, raw prompts/responses in tracing; references never appear in reports |
| Celery/Redis task payloads and results | Deliver scoped opaque work references, not feedback text or identity | 24 hours after task creation, including retries/dead letters | No broker payload dumps; retry exhaustion fails closed; reruns cannot extend source expiry |
| Safe reports, trends, commitments and publication-review ledger | Authorized consumption and prevention of unsafe repeat releases | 365 days after original publication; derivatives expire no later than oldest supporting release | No retained raw supporting passages or source IDs in report/ledger; ledger stores policy version, safe release identity and decision state only |
| Content-free diagnostics and security access audit | Reliability, access investigation and expiry verification | 30 days after event | No feedback/draft/report text, prompts, request bodies, URL tokens, credentials or identity-to-content request chains; remove network/user identifiers on feedback routes |

Until published, report candidates inherit raw-source expiry. After raw deletion, retain only already-approved safe outputs; do not reconstruct evidence or regenerate/revise old reports. Expired/missing support prevents new trend generation that needs it. Review ledgers and reports expire together, and weeks outside retention cannot be republished.

Raw drafts, submissions, admission records, analysis sources and broker material are excluded from backups in the MVP. If the chosen storage/backup system cannot enforce that separation, collection/release is blocked. Encrypted backups may include only authorized account/configuration data and approved safe reports; expire backup copies within 30 days of backup creation. Consequently a deleted safe report may remain inaccessible in a backup for at most 30 more days. Restore into isolation, apply expiry/deletion manifests before serving any request, and never restore expired raw material. [#38](https://github.com/alanlima/signal-loop/issues/38)/[#42](https://github.com/alanlima/signal-loop/issues/42) must demonstrate both live deletion and restore behavior; logging backups must obey the same content prohibition and maximum backup expiry.

External AI may process only minimized, scoped inputs necessary for the current analysis; never identity, admission data, exact source timestamps or reusable identifiers. Required provider terms/settings: no training, no human review, zero prompt/output retention (including abuse/debug logs), no application-side prompt logging, and documented deletion behavior for transient execution. If a provider cannot verify these requirements, do not send feedback to it. Local deterministic fakes are the development default. [#39](https://github.com/alanlima/signal-loop/issues/39) owns provider verification and output/privacy evaluation; [#38](https://github.com/alanlima/signal-loop/issues/38)/[#42](https://github.com/alanlima/signal-loop/issues/42) own egress controls, configuration and operational proof. Provider selection is not resolved by this document and remains a production release blocker.

## 8. Synthetic acceptance scenarios

Counts below are internal test inputs, never UI text. `Unavailable` always means the uniform status from section 3. Unless stated otherwise, week is closed and access is authorized. Each published item still needs the full inference review.

| ID | Audience | Counts/context | Expected outcome | Rule |
| --- | --- | --- | --- | --- |
| S01 | Team and manager | Roster 12, zero submissions | Unavailable; no zero-response explanation | P1/P5/P8 |
| S02 | Team and manager | Roster 4, all 4 respond | Unavailable; cannot relax threshold | P1 |
| S03 | Team and manager | Roster 40, 4 respond | Unavailable despite large membership | P1 |
| S04 | Team and manager | 4 distinct respondents | Unavailable (report threshold minus one) | P1 |
| S05 | Team and manager | 5 respondents; 5 support ordinary review delays; context safe | Publish safe paraphrased delay theme, no counts (exact threshold) | P1/P2/P4 |
| S06 | Team and manager | 6 respondents; 6 support safe delay theme | Publish safe theme, no counts (threshold plus one) | P1/P2/P5 |
| S07 | Team and manager | 8 respondents; theme A supported by 4, B by 5 | Omit A and its derivatives; B may publish | P2/P8 |
| S08 | Team and manager | 8 respondents; theme support 5 / 6 | Either theme may publish after all gates; evidence threshold boundaries equal theme boundaries | P2 |
| S09 | Team and manager | 8 respondents; every theme has fewer than 5 supporters | Entire report unavailable because no safe content remains | P2/P8 |
| S10 | Processing then team/manager | Rowan sends 6 answers, 3 follow-ups, 2 Cedar sections and retries; 3 others respond | Count 4, unavailable; not 15+ | P1/P2 |
| S11 | Processing then team/manager | Rowan answers Cedar and Birch, with 3 other Cedar contributors | Cedar remains 4; Birch does not raise Cedar count | P1 |
| S12 | Team and manager | Eligible report, distinct support count missing or safety check times out | Withhold affected item; if eligibility unknown, entire report | P8 |
| S13 | Team and manager | 5 supporters; proposed text names Morgan | Remove name and re-review entire claim; publish only if generalized claim still safe and grounded | P4 |
| S14 | Team and manager | 5 supporters identify sole overnight DBA, exact date and rare outage | Withhold incident even without name; independent safe process theme may remain | P4/P8 |
| S15 | Manager evidence | 5 safe supporters; proposed verbatim quote | Quote forbidden; separately grounded safe paraphrase may publish | P4 |
| S16 | Manager evidence | 5 support shared review delays; synthesis invents an argument | Omit invented example; labelled grounded generic example may replace it before first release | P2/P4 |
| S17 | Readers of Cedar and Birch | Each report has 5; only Rowan overlaps; repeated rare narrative | Suppress narrative in both candidates or matching new item if old release exists | P4/P6/P8 |
| S18 | Readers of two projects | Each has 6; repeated unique travel narrative; externally known traveller | Withhold repeated story despite counts and broad overlap | P4/P8 |
| S19 | Team and manager history | Both weeks have 5; membership gains/loses one person | Withhold comparison; safe weekly items can remain | P7 |
| S20 | Team and manager history | Prior release from 5; one additional late response | No revision, updated metric, count or second release | P3/P5/P6 |
| S21 | Team and manager history | Stable roster; at least 5 each week; known single new respondent explains change | Withhold trend and any unsafe weekly claim; no participant-set join | P7/P8 |
| S22 | Team and manager history | Safe W1/W3, missing or suppressed W2 | No across-gap trend or improvement claim; generic unavailability at W2 | P5/P7 |
| S23 | Team and manager | Same week reanalysis would add evidence, or privacy defect found | No replacement release; withdraw unsafe item and dependents only | P6/P8 |
| S24 | Team and manager | Critical theme with 4 supporters inside report of 8 | Omit theme, severity rationale and derivative recommendation despite urgency | P2/P9 |
| S25 | Team commitment | Manager approves text identifying only new hire | Withhold; safe generic review-rota action allowed after context check | P4/P9 |
| S26 | Admin / operator | Admin requests raw feedback; operator also a manager | Admin denied; operator risk needs independent separation clearance before collection | Section 1/4 |
| S27 | Team and manager | Consecutive unchanged-roster weeks, 5 safe supporters each, no joint inference risk | Qualitative `Review delays persist` may publish; no numeric deltas | P7 |
| S28 | Team and manager | Eligible numerical total leaves suppressed category of 1 by subtraction | Withhold total/complementary metrics needed for inference, not just small category | P2/P5/P8 |
| S29 | Team compared with manager | Manager rationale would reveal item absent from team summary | Withhold unsafe rationale; separately safe manager detail may remain | P8/P9 |
| S30 | Processing/provider | Provider keeps abuse-monitoring prompts or backup contains raw feedback | No external submission / no collection release until verified compliant | P10/Section 7 |

## 9. Implementation handoff and release blockers

Core MVP choices (counts, windows, audiences, quote ban, immutable releases, suppression and retention) are decided above. This documentation does not mean the system enforces them. No production feedback collection or publication is permitted until all applicable clearance conditions have evidence; implementation inconvenience is not permission to weaken the policy.

| Owner | Required clearance evidence |
| --- | --- |
| [#5](https://github.com/alanlima/signal-loop/issues/5) personal routing | Multi-project personal context does not replicate identifiable narratives; S11/S17/S18 demonstrated without attribution maps |
| [#6](https://github.com/alanlima/signal-loop/issues/6) contracts | Every analysis/release contract carries scope, policy version, expiry and fail-closed safety result; no contributor identities in source contracts |
| [#9](https://github.com/alanlima/signal-loop/issues/9) authorization | Matrix enforced across endpoints, templates/HTMX, exports and caches; admin cannot retrieve raw content |
| [#13](https://github.com/alanlima/signal-loop/issues/13) admission, [#14](https://github.com/alanlima/signal-loop/issues/14)/[#15](https://github.com/alanlima/signal-loop/issues/15) storage/check-in | Reliable one-natural-person/project-week counting without persistent identity-feedback map or cross-context keys; retry and expiry proof; failure withholds |
| [#25](https://github.com/alanlima/signal-loop/issues/25) aggregation, [#27](https://github.com/alanlima/signal-loop/issues/27) trends, [#29](https://github.com/alanlima/signal-loop/issues/29) evidence | Item support, joint history/content inference gates and grounded synthesis demonstrated, including unknown/missing support |
| [#31](https://github.com/alanlima/signal-loop/issues/31)/[#32](https://github.com/alanlima/signal-loop/issues/32) composition, [#34](https://github.com/alanlima/signal-loop/issues/34)/[#35](https://github.com/alanlima/signal-loop/issues/35) report pages, [#36](https://github.com/alanlima/signal-loop/issues/36) commitments, [#37](https://github.com/alanlima/signal-loop/issues/37) history | Independent audience gates, combined-release review, uniform availability, no count leakage, immutable releases and withdrawal behavior |
| [#38](https://github.com/alanlima/signal-loop/issues/38) retention/logging | Every row in section 7 enforced with expiry/deletion tests, redacted diagnostics and task/retry proof; no raw backups |
| [#39](https://github.com/alanlima/signal-loop/issues/39) AI evaluation | Provider zero-retention/no-training/no-human-review verified, minimized inputs and privacy failures tested; unsafe/unverified provider remains disabled |
| [#40](https://github.com/alanlima/signal-loop/issues/40) privacy regression | Translate S01-S30 and audience/retention boundaries into checks; read testing guidelines first; demonstrate unsafe numeric-pass scenarios fail closed |
| [#42](https://github.com/alanlima/signal-loop/issues/42) operations | Access separation including dual-role risk, encrypted storage, egress constraints, backup exclusion/expiry and isolated-restore tests verified; no raw access through observability |

Residual inference remains after these controls. Communicate these limits before collecting feedback. If the deployment cannot meet the stated product-access guarantee, block release instead of describing it as anonymous. No law, certification or provider compliance is asserted by this policy.

## 10. Document self-review

Issue [#4](https://github.com/alanlima/signal-loop/issues/4) review on 2026-09-07: decision values/outcomes (section 2); distinctness/window/worked deduplication (2); report/item boundaries (8 S01-S12); granular withholding (3); audience/operator matrix (1/4); quote/paraphrase/synthesis rules (5, S13-S16); cross-project constraints (5, S17-S18); historical/differencing rules (6, S19-S23/S27); independent derived outputs and availability (3/6, S24-S25/S28-S29); retention/backups/AI (7); executable synthetic scenario inputs/outcomes (8); threat model and owned clearance conditions (1/9). This is a documentation criterion review, not a claim that implementation tests passed.
