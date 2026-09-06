# MVP check-in policy

Version 1.0, decided 2026-09-07. All examples are synthetic. The mandatory [anonymity policy](anonymity-policy.md), established by [#4](https://github.com/alanlima/signal-loop/issues/4), governs publication and retention. These are fixed MVP decisions, not implemented guarantees.

## 1. Projects and initial questions

One weekly journey offers one personal reflection and at most **3 eligible projects**. Eligibility requires active membership in an open project-week not already submitted. For 1-3 eligible projects, preselect all and allow deselection. For more than 3, require explicit selection of 1-3; preselect none. Sort names case-insensitively, with internal project ID breaking ties. Freeze selected order at Begin. Do not add/replace projects after questions start. Removing a section requires confirmation before discarding its answers and does not create a replacement slot.

Unselected projects receive no submission, neutral score or inferred lack of concern. One journey draft per participant/week is the UX limit; after final submission there is no second journey to cover omitted projects. This deliberately bounds effort for people with many memberships. This draft constraint must not become a stored multi-project feedback identifier; [#13](https://github.com/alanlima/signal-loop/issues/13) owns its privacy-compatible enforcement.

With zero eligible projects, show `No projects are available for this week's check-in`. Offer no questions, create no feedback draft and start no clock. Returning later may discover newly eligible projects.

IDs below are field labels. Project names must be escaped when rendered. Text is plain text without attachments/HTML. Length means Unicode code points after CRLF/CR normalization to LF, without silently trimming or truncating input. Client/server counters must agree. Optional whitespace-only text is semantically blank, supplies no evidence, and remains recoverable in the draft until edited/discarded/expired.

| ID | Exact question | Input and allowed stored values | Required / limit |
| --- | --- | --- | --- |
| P1 | How is your energy this week? | Single choice: `low`, `steady`, `high`, `prefer_not_to_say` | Required choice, no default |
| P2 | How manageable is your workload this week? | Single choice: `manageable`, `stretched`, `overloaded`, `prefer_not_to_say` | Required choice, no default |
| P3 | What went well for you this week? | Multiline text | Optional, 0-240 code points |
| P4 | What was difficult for you this week? | Multiline text | Optional, 0-240 code points |
| P5 | What support would help you next week? | Multiline text | Optional, 0-240 code points |
| J1 | How is delivery going in {project_name} this week? | Single choice: `on_track`, `at_risk`, `blocked`, `not_enough_context`, `prefer_not_to_say` | Required for retained project, no default |
| J2 | How manageable is the work in {project_name} this week? | Single choice: `manageable`, `stretched`, `overloaded`, `not_enough_context`, `prefer_not_to_say` | Required for retained project, no default |
| J3 | What should improve or continue in {project_name} next week? | Multiline text | Optional, 0-320 code points |

Display enum labels by replacing underscores with spaces and capitalizing the first letter (for example, `Prefer not to say`). Required means a choice, not a forced substantive disclosure. Declined/unknown choices are valid but supply no evidence or neutral score. A project section with only declined/unknown choices and blank text is non-substantive: omit it from submission and contributor counts. Personal answers never make a section substantive.

Text questions include `Avoid names, exact dates and details that could identify someone.` This guidance does not establish publication safety.

## 2. Personal routing

All personal fields are **private draft reflection only** in the MVP. They are excluded from final feedback, project analysis, AI selection and reports. Before P1 show: `Your personal reflection stays in this draft and is discarded when you submit. Only your selected project answers can contribute to anonymous project summaries.` Also explain that personal reflection is not monitored, delivered to a manager or an emergency/support-request channel. A future routing change needs a reviewed policy version.

| Personal field | Project contribution | Transformation/destination | Withholding |
| --- | --- | --- | --- |
| P1 energy | None | Draft reflection only; no project personal score | Always exclude from submission/analysis |
| P2 workload | None | No propagation; project workload comes only from separately answered J2 | Always exclude; never fill project defaults |
| P3 wins | None | No paraphrasing/copying/source reference | Always exclude even apparently safe text |
| P4 challenges | None | No inferred project or copied narrative | Always exclude even high severity/project mentions |
| P5 support | None | No manager message or inferred commitment | Always exclude |

All five expire with the draft under #4: earliest of submission, week closure or seven days after creation. Example: Rowan writes `As the only overnight specialist, I handled the rare outage` in P4 and selects Cedar/Birch/Maple. All project payloads exclude that narrative. A stretched P2 does not fill any J2. Rowan can independently answer project workload differently. Do not suggest copying personal text into project fields.

J1/J2/J3 and project follow-ups route only to their explicitly selected project-week, subject to admission and #4 publication gates. If Rowan manually repeats a unique narrative across projects, joint cross-project inference checks can withhold it even at five contributors. Do not persist an identity-to-feedback map or shared personal source ID for that review. Selection, omissions, progress, skips and timing are not manager-analysis features.

## 3. Follow-up budget and ordering

Initial budget is **5 + 3n**, at most **14** questions for n<=3 selected projects. Global adaptive budget is **2 slots per journey**, at most **1 per project**, and **0 personal follow-ups**. Maximum offered questions: **16**. Offer P1-P5, then J1-J3 for each project in frozen order, then follow-ups. Personal answers never influence selection.

AI may select/suppress only this fixed catalog, never generate arbitrary question text:

| ID | Exact question | Trigger/priority | Input |
| --- | --- | --- | --- |
| F1 | What change would most help delivery in {project_name} next week? | J1 blocked: priority 1; at_risk: priority 3 | Optional multiline, 0-240 code points |
| F2 | What change would make the workload in {project_name} more manageable? | J2 overloaded: priority 2; stretched: priority 4 | Optional multiline, 0-240 code points |

For each project choose its lowest-numbered eligible priority. Sort candidates by priority then frozen project order. Reserve at most the first two distinct projects before any AI request. AI may suppress a reserved candidate as redundant, but may not reorder, replace projects or expand the budget. Suppressed/failed candidates close their slots without replacement. No text answer invents a new candidate. AI has a **2-second wall-time deadline per reserved slot**; invalid output/timeout closes it and late output is ignored.

A shown, skipped, suppressed or failed slot cannot be replenished by retry, refresh, back navigation or a new AI call. Optional text and follow-ups may be skipped explicitly; a skip generates no signal or replacement. Whole projects may be skipped with confirmation and discarded answers. Required choices may be declined. Saving/leaving does not submit. If every project is skipped/non-substantive, show `No project feedback to submit`; offer discard or return to already-seen questions and consume no submission credentials.

## 4. Progress and worked timing

Freeze progress denominator **D=5+3n+2** at Begin. Show `x of D question slots complete`. A slot resolves on valid saved answer, explicit optional skip, confirmed project removal or adaptive closure. Close unused adaptive slots after allocation. Project removal does not shrink D. Review/submission is separate. Back alone does not change progress; invalidating an answer or clearing a required choice reopens its slot and reduces x. Never claim all complete while a shown answer is invalid/unresolved.

Estimates allow 15 seconds selection, 5 seconds each structured choice, 20 seconds each personal text, 25 seconds per J3, 20 seconds per follow-up, 20 seconds review. These are design estimates, not measurements; readers and typists vary.

| Journey | Exact sequence | Progress | Estimated duration |
| --- | --- | --- | --- |
| Zero eligible | No questions; availability message | No denominator/bar/timer | About 5 seconds |
| One project Cedar | P1-P5; Cedar J1,J2,J3; Cedar F1 when J1=blocked/J2=stretched | D=10; personal 5/10; project 8/10; unused slot closes to 9/10; F1 answered/skipped gives 10/10 | 15+10+60+10+25+20+20=160 seconds (2m40s) |
| Six eligible, select Birch/Cedar/Maple | P1-P5; Birch J1-J3; Cedar J1-J3; Maple J1-J3; Birch F1 (blocked); Cedar F2 (overloaded); Maple at_risk gets no slot | D=16; personal 5/16; projects 8/16,11/16,14/16; follow-ups 15/16,16/16; other three projects receive nothing | 15+10+60+3*(10+25)+40+20=250 seconds (4m10s) |

One project with no eligible follow-up goes from 8/10 to 10/10 when both slots close. Two projects have D=13, sequence P1-P5 then each J1-J3 then ranked follow-ups. The five-minute target never justifies exceeding these limits.

## 5. Ten-minute boundary and recovery

Start a server-authoritative **600-second elapsed clock** when Begin creates the draft. Selection before Begin is excluded. Refresh, back, inactivity, browser closure and resume never reset or pause it. Begin again resumes the same draft. Concurrent tabs share authoritative budget/time and need conflict-safe saves. Start time/progress belong only to transient drafts, never submitted feedback metadata.

At elapsed >=600 seconds stop offering **all new questions**, cancel pending selection and ignore late AI output. Close unseen slots as not offered, without adding that reason to feedback. Show a finish/review path preserving every entered answer. Allow editing/clearing already-seen answers, explicitly skipping existing questions/sections, submitting valid substantive project feedback, saving/leaving or intentional discard. Never auto-submit, silently truncate, clear entered text or consume admission credentials at timeout.

Unseen required questions cannot be introduced after timeout. Incomplete projects can only be omitted after explicit participant confirmation; no invented values. If a personal required question was unseen, waive it at timeout because personal reflection is not submitted; retain any entered personal text until normal draft deletion. A previously seen required choice remains editable/declinable on review. The ten-minute cap ends new elicitation, not accessibility time for review/correction/decision; the finish view can remain open past ten minutes within draft lifetime. Resume after twenty minutes opens that finish view, not a fresh adaptive stage.

Draft expiry is earliest of successful submission, week closure or seven days after creation. Display the exact UTC expiry before Begin and on save/finish. A save acknowledgement means persistence succeeded; if save fails keep text visible, explain failure, permit retry and prevent accidental navigation without warning. A hard privacy expiry is pre-disclosed, warned about in an open draft and explicitly explained on late return; expired content must not be reconstructed. No automatic copying into next week.

Final submission failure/ambiguous network response preserves recoverable answers within expiry until #13 reconciles the outcome. Established success deletes the draft and personal reflection. Window closure blocks old-week submission even if its clock has time left. Revoked membership makes that project ineligible; preserve other answers within lifetime and require acknowledgement before removing the invalid section. Do not silently partially submit; atomic retry semantics belong to #13/#21.

## 6. Boundary examples

| Input/event | Outcome |
| --- | --- |
| Optional P3/J3 blank or whitespace-only | Valid explicit Next/skip, no evidence; no automatic page-load completion |
| Required P1 missing | Unresolved slot/error; allow prefer_not_to_say; no steady default |
| P3 exactly 240 code points | Valid, all characters retained |
| P3 241, J3 321, follow-up 241 | Invalid; preserve whole draft value, show count/limit, block submission until corrected or explicitly cleared; never truncate |
| Emoji/newline | Count code points after newline normalization, not bytes/UTF-16 units; multi-code-point emoji counts each code point |
| Skip F1 | Close slot permanently; no replacement or negative inference |
| AI exceeds 2 seconds | Close reserved slot, show Continue without an extra question, ignore late output; answers intact |
| AI wrong project/ID or invented prompt | Close as failed; do not render dynamic prompt or increase budget |
| Back/edit J1 after F1 | Preserve answers and spent slots; no new follow-up. If edit invalidates shown follow-up eligibility, visibly mark its answer excluded from final payload and require acknowledgement; otherwise retain it |
| Remove Maple | Confirm discard; omit its payload, resolve its slots with unchanged D; no replacement project |
| Three eligible follow-up projects | First two ranked candidates only; third's initial answers still count subject to privacy |
| Boundary during typing | Keep text editable with finish controls; no new prompt/forced submission |
| Boundary while AI pending | Ignore arriving result; finish existing draft |
| Refresh at 590 seconds | Same answers/start/slots/D; only ten seconds for new questions |
| Resume at twenty minutes before expiry | Existing finish/review only; no reset |
| Resume after expiry | Explicit expiry outcome, no recovered content or silent new-week copy |
| Save/network/submission failure | Visible failure, recoverable text within expiry; retry reconciliation, not a new journey |
| Only unknown/declined project choices and blank text | No substantive feedback or count increment; discard/return options |
| Urgent personal support text | Never deliver to manager/AI/projects; pre-question copy explains it is not monitored |

## 7. Handoffs and self-review

Core routing/budget choices are resolved above. Protocol feasibility and enforcement remain release conditions, not permission to weaken #4.

| Owner | Required clearance |
| --- | --- |
| [#4](https://github.com/alanlima/signal-loop/issues/4) | Publication threshold/content/inference/retention authority; participant-only progress never becomes report data |
| [#6](https://github.com/alanlima/signal-loop/issues/6) | Exact fields/enums/catalog; final payload excludes personal fields, timing/progress and shared multi-project response IDs |
| [#12](https://github.com/alanlima/signal-loop/issues/12) | UTC windows compatible with #4 and draft closure |
| [#13](https://github.com/alanlima/signal-loop/issues/13) | Draft lifecycle, conflict-safe saves/budgets, one-journey UX, single-use admission and ambiguous retry reconciliation without persistent identity-feedback mapping; prove compatibility before collection |
| [#16](https://github.com/alanlima/signal-loop/issues/16), [#17](https://github.com/alanlima/signal-loop/issues/17) | Exact input/limit/omission behavior and recoverable draft validation |
| [#19](https://github.com/alanlima/signal-loop/issues/19), [#20](https://github.com/alanlima/signal-loop/issues/20) | Two-slot cap, ordering/deadline, progress and authoritative clock/finish behavior |
| [#21](https://github.com/alanlima/signal-loop/issues/21) | Atomic final submission, no silent partial success; omit personal/non-substantive data and delete draft after established success |
| [#38](https://github.com/alanlima/signal-loop/issues/38), [#40](https://github.com/alanlima/signal-loop/issues/40) | Expiry/no correlation logs and downstream scenario checks; test authors read testing guidelines |

Self-review against #5: exact fields/requirements/types/values/limits (1); full routing/leak examples (2); numeric allocation/order/skips/many projects (1/3); zero/one/many timing/progress (4); clock/resume/preservation (5); every requested edge case (6); linked privacy/draft authority and resolved choices (7). Documentation only: no code, forms, dependencies, vendor selection or automated tests.
