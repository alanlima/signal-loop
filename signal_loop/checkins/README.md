# Private check-in drafts (#16 and #17)

The current check-in shell route now offers the exact P1-P5 form from
[_docs/check-in-policy.md](../../_docs/check-in-policy.md). Personal answers stay
only in `PersonalDraft`, linked to the identity-side global journey. They are never
sent to admission, the progression callback, feedback, analysis or a report.
No draft admin registration/default permissions exist. All forms use CSRF-protected
POST, escaped Django rendering, fixed field names, no-store responses and sensitive
POST annotations; text never enters a URL or application log.

`CHECKIN_PRINCIPAL_PROVIDER` defaults to the denying admission provider. Production
verification remains #13/#42's gate. The view gathers only verified, active snapshot
eligibility across the signed-in person's organisations; forged project selections
and forged shell query scopes cannot start a draft. One to three projects preselect
all, more than three preselect none, and Begin freezes up to three in name/ID order.
The exact selected expiry preview uses public window boundaries and the global
UTC week-end. Server validation independently enforces that frozen expiry.

Begin creates the existing #14 journey and private draft atomically. GET does not
start a clock. Resume and Next/Back preserve start, selection, expiry and answers.
Personal text fields enforce 240 Unicode code points after CRLF/CR normalization;
required choices have no default and permit declining. Browser counters use
`Array.from` and do not apply HTML's incompatible UTF-16 maxlength. Invalid input
stays visible and recoverable in the transient draft, as #5 requires; it cannot
advance. Existing Django request-size limits still apply. No input is silently
trimmed or truncated. Optional whitespace is preserved without inferred support.

A principal lock and draft revision protect saves; stale posts keep their unsaved
text visible and do not replace newer stored answers. Successful save acknowledgements
follow the database transaction. Storage/progression errors show fixed retry text
and keep entered answers without exposing exception details. The fake progression
callback takes **no arguments**, so it cannot receive P1-P5 or accidentally become
a feedback submission. Next advances to the frozen project sections. #19/#20/#21
own adaptive questions, timer and submission integration. No final feedback is
written or credential consumed by these forms.

Project sections use exactly J1/J2/J3 and the #5 choices and 320-code-point J3
limit. `ProjectDraft` stores these transient answers under the same private draft;
deleting or expiring the parent cascades to every section. Full-page and HTMX
Next/Back/save preserve each section independently and show current project and
progress. The final placeholder explicitly says submission is unavailable.
Unselected IDs, duplicate/extra fields and unauthorized organisation scopes are
rejected. Authorized combined selections across organisations remain supported.
Every request rechecks current eligibility. A revoked section requires explicit
removal acknowledgement; removing it preserves other sections and cannot add a
replacement or extend expiry. Removing every section shows an empty finish path.

Expiry is the earliest selected local close/global UTC week-end/seven-day cap,
frozen at Begin. Reads and writes deny expired drafts; access atomically reconciles
all of the person's expired admission journeys and removes expired private drafts,
even across a new global week. Reconciliation seals the old slots, clears their
transient selection/start/expiry and cancels old credentials without cancelling a
new week's rotated credential. Expired content is never reconstructed.
Discard needs explicit confirmation, deletes the private row and seals the global
week. On a later UTC week a new eligible journey may start without old answers.
#38 still owns scheduled deletion at deadlines and replica/cache/backup enforcement;
this request-bound handling does not claim a background retention worker exists.

## Reproducible synthetic browser review

Use disposable local PostgreSQL/Redis and **only synthetic reflection text**.
The explicit review settings are separate from default/CI settings. The seed command
refuses to run without them and maps only the named synthetic account to a fixed
verified-person UUID; arbitrary accounts have no fallback identity.

```powershell
uv run --env-file .env.issue1 python manage.py migrate --settings=signal_loop.settings_personal_review
uv run --env-file .env.issue1 python manage.py seed_personal_review --settings=signal_loop.settings_personal_review
uv run --env-file .env.issue1 python manage.py runserver 127.0.0.1:8002 --noreload --settings=signal_loop.settings_personal_review
```

Substitute your disposable environment-file path/available port. Open
`http://127.0.0.1:8002/app/check-in/`, log in as `synthetic_personal_review` with
`synthetic-review-password`. The fixture creates Cedar/Brisbane and Birch/New York
in their currently open local windows. It adds no production principal provider.
Do not discard/expire the fixture journey until the end of review: the approved
global-week rule correctly prevents another Begin in that week. Rerunning the seed
command does not erase an existing journey or reset its expiry.

At 360px: check project selection/expiry preview, visible Tab focus, required
indicators, optional blank values, long text errors, safe HTML-like text, Next,
Back and a fresh-page resume. Expected: no horizontal page overflow, no unexpected
personal text in URLs, and no feedback submission. To test the fake failure, stop
the owned server, set `$env:CHECKIN_REVIEW_FAIL='1'`, and restart the same command.
Next must retain answers with a retry message. Remove that environment variable
and restart to recover; do not start overlapping servers or use a stale port.

After personal Next, enter different synthetic J1/J2/J3 answers in Birch and Cedar.
Verify project progress, Next/Back, save/resume and J3 over-limit errors in full-page
and HTMX requests. Adaptive F1/F2 controls must be absent. The project review
placeholder must not claim submission. Test section removal only after navigation:
it is permanent within this frozen journey, and removing both gives the empty path.

```powershell
uv run --env-file .env.issue1 pytest --postgres signal_loop/checkins/tests signal_loop/accounts/tests/test_shell.py
uv run --env-file .env.issue1 pytest --postgres
uv run ruff check .
```

Request tests cover exact questions/labels, denied/forged selection, combined scope,
no implicit selection above three, valid/over-limit Unicode, optional blanks,
normalization, safe rendering, fake/storage failures, owner-only resume, stale saves,
expiry/discard and no personal writes to feedback. Independent browser QA records
mobile and keyboard results before closure. No dependency or external service added.
