# Restricted admission service (#14)

Implements the local credential/transaction boundary from
[_docs/anonymous-submission.md](../../_docs/anonymous-submission.md). This app has
no HTTP endpoints, admin registrations, raw-feedback models or production identity
provider. All model default permissions are empty. Callers are trusted application
services responsible for authenticated request transport and CSRF.

## Interface

- `issue(user=..., scopes=[(project_id, window_id), ...], provider=...)` begins or
  resumes a combined journey. It returns global UTC week, frozen expiry and opaque
  per-project credentials. There must be 1-3 unique projects in captured, currently
  open local windows, accessible to this account. A resume preserves selection,
  start and expiry while rotating credentials; older tokens become invalid.
- `redeem(user=..., week=..., claims=issued.credentials, sections=..., sink=...,
  provider=..., clear_draft=...)` validates every claim before consuming any slot.
  A successful transaction returns `complete`; all-non-substantive sections return
  `no_feedback` with no consumption. Repeated redemption is rejected. The separate
  own-status call reconciles a lost response, never by querying feedback content.
- `own_status(user=..., organisation=..., week=..., provider=...)` returns only
  `open`, `complete` or `unavailable` for the verified person's global week. The
  organisation is a trusted verification context, not a roster filter. Discarded,
  expired, missing and retention-expired journeys never masquerade as submitted.
- `discard(...)` seals the person's week and cancels its credentials. #16/#21 must
  coordinate actual draft deletion with this same transaction; no draft content
  exists in this app. Successful redemption's `clear_draft()` hook already runs
  in the sink/consumption transaction and rollback is tested.

`provider(user, organisation)` must return `VerifiedPrincipal(UUID)` or no result.
The default always denies. It must resolve all aliases and organisations to the
same verified natural person. No account, email or membership ID is a fallback.
Tests inject an explicit synthetic directory: two Rowan accounts share P1, Avery
has P2, an unverified account gets nothing. This proves alias mechanics only.
Production issuance remains blocked by #13 R1 until #42 supplies actual verified
provisioning and evidence. Provider injection is a trusted server configuration,
never request-controlled input.

`clock` is an internal test seam; production callers leave it at server UTC now.
Scopes, user/principal resolution, revocation and current time are checked after
locks, with another time check immediately before mutations. No supplied client
timestamp grants eligibility. #21/#24 must use the same window locks for final
closure integration as the approved protocol requires.

## Sink and draft handoff

Input sections are `{project: int, week: local_Monday_ISO_date, answers: {...}}`.
Only J1/J2/J3/F1/F2 keys and string values enter the transport shape; J1/J2 enums,
text limits, normalized newlines, follow-up triggers and maximum one follow-up per
project/two total are checked by `signal_loop.contracts.feedback`, shared with the
#15 persistence sink. Personal fields and unknown envelope keys reject.
Non-substantive sections do not consume participation. #20/#21 additionally prove question presentation/budget, draft
revision, explicit removal acknowledgement and full frozen-draft validation.

The sink receives independent dictionaries containing exactly `project`, local
`week`, `schema=project-feedback/1.0`, `privacy_policy=1.0`, and `answers`. It never
receives identity, credential, participation, draft/global-week or shared response
IDs. It must use the current Django connection, raise on any failure, perform no
network/independent commits, and return no source IDs. No transaction outbox stores
the submitted body. The optional cleanup hook has the same rules; #21 must supply
it when actual drafts exist. #14 has no submitted or personal content store.

The tests' sink and fake draft use temporary-purpose tables created only inside
the disposable test database. Their writes participate in the real PostgreSQL
transaction, so a failure after the first section or after draft deletion proves
rollback of sink, consumption, completion and cleanup rather than merely checking
an in-memory callback list. #15/#21 supply real models/adapters later.

## Concurrency, secrets and lifetime

Transactions lock organisations/windows in deterministic ID order, then the
verified principal, current account/membership rows and participation/credentials.
The principal lock serializes aliases and differing project selections in the
global week, including first issuance. Database uniqueness enforces one global
journey per principal and one participation slot per principal/project/window.
Concurrent replay commits once; the waiting request re-reads state and refuses.

Each secret uses `secrets.token_urlsafe(32)` (256 random bits); only its SHA-256
verifier is stored. `hmac.compare_digest` verifies it, bound to current principal,
project/window and purpose. Resume rotates verifiers without resetting consumption
or expiry. Credential repr hides the secret. Public errors contain only fixed
codes, including `retryable_failure`; no secret or underlying sink exception.
Authenticated transport rate limits and operational controls remain #21/#42.

Begin freezes the minimum selected local close, global UTC week-end and seven-day
maximum. Completion, discard or expiry seals the week and clears transient scope
maps/start/expiry, leaving only principal/global week/state/public retention bound.
Selection changes cannot reset expiry or replace projects. Later status checks of
an expired old journey cannot cancel newly rotated credentials in the next global
week. Consumed local windows remain consumed even across that global rollover.

Participation/credentials retain no response identifiers, payload fingerprints,
content or precise submission timestamps. Participation retention ends seven days
after its local window closes; journey terminal state ends seven days after global
week-end. Expired records become inaccessible through the service; scheduled
deletion/backup exclusion is #38/#42. Raw model mutation, arbitrary sink callbacks
or infrastructure SQL bypass the trusted service boundary and are not product APIs.
No routine operator/raw-content access or perfect-anonymity claim is introduced.

## Verification

Against disposable PostgreSQL (substitute your own configured env-file path):

```powershell
uv run --env-file .env.issue1 pytest --postgres signal_loop/admission/tests
uv run --env-file .env.issue1 pytest --postgres
uv run ruff check .
uv run --env-file .env.issue1 python manage.py makemigrations --check --dry-run
```

Fixtures cover mandatory verification, aliases, inconsistent cross-organisation
principal resolution, exact opening/expiry, unknown/tampered/swapped/wrong-week
claims, replay and lost-response reconciliation, real concurrent alias redemption,
partial sink/cleanup rollback, revoked membership, non-substantive omission,
discard/expiry sealing, frozen resume state, and global/local rollover isolation.
No dependencies or database extensions are added.
