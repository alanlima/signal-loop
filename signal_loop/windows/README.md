# Weekly windows and eligibility

The window service is an identity-side admission boundary. It exposes no HTTP
participant directory or admin registration; analysis, feedback and reports must
not import eligibility models or join their identities. No feedback, source ID,
submission state or credential is stored here. A window roster is not a distinct
contributor count. Admission proof belongs to #13.

## Time contract

Per the user's 2026-09-07 decision for #12, a week starts Monday 00:00 in the
organisation's configured IANA timezone and ends the following local Monday
00:00, open-inclusive and close-exclusive. The trusted scheduler/configuration
caller passes that organisation timezone to `create_weekly_window`; no global
timezone default is inferred. The window durably records the timezone and local
Monday date, plus both instants converted independently to UTC. Existing windows
cannot change when configuration changes. `week_start` is a local date, not the
UTC calendar date of opening; its ISO year can differ from its calendar year.

`weekly_bounds` validates Monday and IANA timezone. Ambiguous midnight uses the
first occurrence (`fold=0`); a nonexistent Monday midnight is rejected for an
explicit scheduling decision rather than silently shifted. UTC comparisons and
aware inputs ensure equivalent local/UTC instants return the same result.
New York's 2026-03-02 week is 167 elapsed hours, and 2026-10-26 is 169 hours.
Brisbane's 2026-09-07 opening is 2026-09-06T14:00Z. No fixed 168-hour arithmetic
is used to compute closing. At closing, old-week eligibility is empty; an adjacent
materialized window can become eligible immediately. Scheduled creation is #24.

## Snapshot and membership contract

All supported window creation paths (`objects.create`, instance `save`, and the
service) atomically capture active project memberships of active accounts,
organisation memberships, projects and organisation. Capture happens once when
the window is materialized; the opening scheduler must materialize at opening,
not pre-create future snapshots. Tests explicitly materialize synthetic dates.
Do not rebuild snapshots on lookup, membership edits, retries or scheduler runs.
Frozen roles are historical facts; membership/project associations are immutable
in the membership module. Project names are live display labels.

- Joins after capture become eligible in the next captured window, never by adding
  rows to an existing snapshot.
- Removal/deactivation does not rewrite the snapshot. Lookup additionally checks
  current account, organisation, project and membership activity, so revoked
  projects are unavailable immediately. Reactivation restores eligibility only
  for memberships that were originally captured.
- Role changes preserve `role_at_open`. Current report/manager authorization must
  use live authorization predicates, not this historical role.

`eligible_projects(user=authenticated_user, organisation=..., at=aware_instant)`
returns an immutable tuple of minimal window/project IDs, display names and frozen
roles, sorted case-insensitively by project name then ID. Zero projects returns
an empty tuple. Trusted admission callers must supply the authenticated principal,
never accept a participant ID supplied by another user. This is eligibility only:
#13/#14 add already-submitted/credential decisions and recheck revocation at final
admission. No source/content join may be added to this result.

## Concurrency, integrity and retention

Each validated window save opens a PostgreSQL transaction, locks its organisation
row with `SELECT FOR UPDATE`, checks intersecting UTC intervals, and saves the
window and complete snapshot together. This serializes competing creates even
when the organisation has no prior windows. Adjacent intervals and independent
organisations are permitted. A timezone change that creates even a partial
overlap is rejected. Unique organisation/local-week and positive duration database
constraints supplement that serialized range check. Existing window saves and
bulk mutation APIs are rejected; snapshots cannot be added or edited through
normal saves or managers. No database extension or new package is required.

The supported integrity boundary is validated model/service writes under Django's
default PostgreSQL READ COMMITTED isolation. Raw SQL, private ORM escape hatches
and infrastructure users bypass application invariants; they are not supported
writers. Operational access controls remain #42. The concurrency test uses separate
connections and different week identities, so the unique-week constraint cannot
mask range validation.

Snapshots are restricted admission/participation material under anonymity P10:
maximum retention is seven elapsed days after closure, excluded from raw backups.
Lookup stops exposing them at closure. `expire_eligibility(at=...)` provides the
operations-only deletion boundary at the retention deadline while retaining
non-identifying window schedules. #38 owns scheduling, access enforcement,
replica/cache deletion and backup proof; no automated expiry claim is made here.

Run `uv run --env-file .env.issue1 pytest --postgres signal_loop/windows/tests`
against disposable local services (or substitute your configured environment file).
