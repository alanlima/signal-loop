# Integrated private journey (#20)

The check-in route connects personal, frozen project, optional adaptive and finish
steps. The denominator stays `5 + 3n + 2` from Begin, including removed projects
and unused adaptive slots. Only valid saved answers, explicit skips/removals and
adaptive closure resolve slots. Invalidating a required answer lowers progress;
Back alone cannot complete a previously unanswered optional slot.

The sole elapsed clock is admission `Journey.started_at`, created at Begin.
Neither refresh, Back, save nor resume changes it. New elicitation stops at
min(start + 600 seconds, hard draft expiry). Clock state contains no response
content. The UI displays a countdown and exact deadline; the server decides every
transition. Reaching the deadline does not navigate away from unsaved browser
text. The next save/request opens finish, preserving typed values. No new unseen
questions are rendered there: participants can edit previously seen questions,
acknowledge removal of unseen/incomplete projects, save, skip, preview finish or
discard. Previously unseen personal questions are waived at timeout. Already-seen
invalid questions still require correction or permitted removal/skip.

`seen_slots`, allocation state and `adaptive_answers` are separate private draft
fields. The migration reconstructs seen slots only from existing saved answers;
it never resets start or introduces unsaved questions into an expired allowance.
All this state cascades with the draft on discard/expiry, and no copy goes to
feedback or a report. The hard expiry remains the frozen earliest local window
close/global UTC week-end/seven-day cap. #38 owns scheduled deletion enforcement.

`DraftAllocationStore` implements #19 against PostgreSQL. First allocation,
permanent claim and result are committed in separate atomic row-lock transactions;
provider work occurs after the personal/project transaction exits. Concurrent
claims have one winner. Reconstructed stores reuse the same allocation; a claim
without a completed result closes safely rather than reissuing. Pending/unused
slots close at the elapsed boundary. Membership is rechecked before offering
adaptive output. #18 still enforces min(two seconds, remaining allowance).
Provider failure gives a usable review continuation and consumes its slot.

Follow-up answer edits/skips persist with the private draft. Editing J1/J2 can
make a shown follow-up ineligible: the finish page preserves its text, visibly
excludes it and requires acknowledgement before any final payload can be built.
The exclusion never creates a replacement question. Finish fields have unique
labels/error IDs and preserve validation, stale-tab and storage-failure values.
The browser warns before leaving or submitting another form with unsaved edits;
save edited sections before moving between separate finish forms.

## Final-submission boundary

The button is explicitly **Finish practice check-in**. The default
`signal_loop.submission.services.preview_submission(sections)` receives only
validated substantive project/local-week J/F sections. No P1-P5, draft ID,
principal, clock, budget or shared feedback identifier reaches that seam.
`CHECKIN_FINAL_SUBMISSION` can replace the callable in controlled tests.

`preview_complete` shows that no feedback was submitted. It writes no feedback,
consumes no admission and leaves the recoverable draft intact until discard/expiry.
It never sets admission `completed`, whose protocol meaning requires submission.
Invalid/incomplete/revoked sections or unresolved follow-ups block the preview;
failure preserves answers. #21 must replace this seam with credential redemption,
atomic persistence and cleanup, and replace practice copy with real completion.

## Reproducible keyboard/mobile review

Use only synthetic data and a fresh owned server. Apply migration0003 before
restarting; old `--noreload` processes do not pick up code changes.

```powershell
uv run --env-file .env.issue1 python manage.py migrate --settings=signal_loop.settings_personal_review
uv run --env-file .env.issue1 python manage.py seed_personal_review --settings=signal_loop.settings_personal_review
uv run --env-file .env.issue1 python manage.py runserver 127.0.0.1:8002 --noreload --settings=signal_loop.settings_personal_review
```

Choose an available port/disposable environment file. All accounts use password
`synthetic-review-password`; only explicit review settings verify these synthetic
principals. The seed preserves existing journeys and never resets a weekly seal.

| Account | Fixture and expected flow |
| --- | --- |
| synthetic_journey_ordinary | One project. P1/P2 choices and optional texts; on_track/manageable with optional J3; no adaptive question, 10/10, practice finish. |
| synthetic_journey_many | Four eligible projects, none preselected. Choose three. Use blocked for the first, overloaded for the second, at_risk for the third: exactly two adaptive questions, fixed16 slots. Skip one, answer the other, review and practice finish. |
| synthetic_journey_zero | Authorized shell project but no current window: explicit no-project message, no Begin, timer or questions. |
| synthetic_personal_review | Existing Birch/New York and Cedar/Brisbane combined fixture, retained for #16/#17 regression. |

At 360px use Tab/Shift+Tab/Enter through selection, personal, projects, follow-up
and review; verify no horizontal overflow, visible focus and unique labels.
Test over-limit text, Next/Back, skip, saved-page resume and a failed/stale save.
Use distinct synthetic answers per section; preserve each across validation.
Before navigation, save edited finish forms. Discard only at the end: it seals
the week. To simulate AI timeout, set `CHECKIN_REVIEW_AI_FAULT=timeout` and restart
the owned server **before initial allocation**; changing it later cannot refill
a spent slot. Remove the variable and restart for normal behavior.

Controlled-clock tests cover599/600-second boundaries, typed text at timeout,
unseen sections, removal, unchanged start, progress, migration, expiry and real
PostgreSQL concurrent claims. The separate #41 task owns timed whole-experience
measurement; this implementation does not claim a measured five-minute result.

```powershell
uv run --env-file .env.issue1 pytest --postgres signal_loop/checkins/tests
uv run --env-file .env.issue1 pytest --postgres
uv run ruff check .
```
