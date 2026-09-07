# Opening invitations (#22)

The user-approved rule is **one invitation per verified natural person per
organisation window**, even across projects and account aliases. Delivery uses
only that person's designated verified primary email. Missing, multiple, invalid
or mismatched primary contacts withhold; never select the first alias email.

`send_window_invitations(window_id=..., principal_provider=...,
contact_provider=..., transport=deliver, clock=timezone.now)` is the #24 boundary.
Reinvoke the same window for retries; it consults durable `InvitationDelivery`
state instead of resending everybody. No periodic dispatcher or reminders are
introduced. #24 owns scheduling, including its separately approved late-capture
rule; this service consumes the existing immutable #12 snapshot.

The trusted principal provider is the same `VerifiedPrincipal(UUID)` contract
as #14, resolving all aliases to one natural person. `contact_provider(principal,
organisation)` returns `VerifiedPrimaryContact(principal, addresses=(... ,))`
with exactly one designated verified address. These are server configuration
interfaces, never claims accepted from a request. Set `CHECKIN_PRINCIPAL_PROVIDER`
and `INVITATION_CONTACT_PROVIDER` in trusted settings. Defaults do not infer
identity or contact from account IDs/emails. #42 must supply real verified
provisioning/primary-contact evidence before production sending.

Only captured memberships in the target window qualify, with live user,
organisation membership, project membership, project and organisation activity
rechecked before each committed claim. At least one eligible alias is sufficient;
late joins and other organisations cannot add recipients. No feedback/participation
status is queried, and invitations never identify respondents/nonrespondents.
The message contains only a neutral authenticated `/app/check-in/` link. No user,
principal, window, project, participation or credential identifier is in its URL.

## Delivery, concurrency and ambiguity

PostgreSQL enforces unique `(window, principal)` and serializes claims under the
window lock. A short transaction commits SENDING before transport. It rechecks
the open-inclusive/close-exclusive window and live eligibility immediately before
the claim; that is the authorization instant. Later revocation cannot recall
an already accepted message. The transport runs outside the transaction with
10-second Django email timeout; no external effect is rolled back with database
state. Successful transport marks SENT, skipped on every rerun.

`DefiniteDeliveryFailure` means the transport guarantees no acceptance; FAILED
remains retryable. Django's explicit zero-send result is such a failure. Unknown
exceptions are AMBIGUOUS, because the provider may have accepted the email before
the connection failed. AMBIGUOUS is not retried automatically. A crash after claim
or acceptance leaves SENDING; a rerun after two minutes quarantines it as AMBIGUOUS.
A live SENDING claim is skipped. Concurrent commands cannot claim it again.

This is not an exactly-once transport claim: without provider idempotency/status,
one cannot distinguish accepted-but-unacknowledged from never sent. Reconciliation
must use provider evidence under #42; do not reset ambiguous rows or resend all
recipients to recover. Missing-contact WITHHELD rows may retry after directory
correction. Closed windows never send, including failures awaiting retry.

The delivery model contains only principal/window, state, attempt count/start and
fixed retention deadline, never email/body/feedback/source/credential fields. No
admin/default permissions expose it. Identity-side invitation state expires seven
days after closure; `expire_deliveries(at=...)` is the operations deletion boundary,
with #38 owning scheduled/replica deletion. Exact attempt times remain identity-side
operational data and are never joined to feedback. No transport exception is logged.

## Local review and command

Default email delivery is Django console; file and locmem backends are also
supported. Console/file output intentionally contains only invitation email, not
response content. Files default to ignored `.local-email/`; treat any other chosen
file path as local restricted output and do not commit it.

Reproducible synthetic-only review (PowerShell, repository root):

```powershell
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py seed_invitation_review --settings=signal_loop.settings_invitation_review
# Replace 123 with synthetic_window printed above.
uv run --env-file .env python manage.py send_invitations 123 --settings=signal_loop.settings_invitation_review
uv run --env-file .env python manage.py send_invitations 123 --settings=signal_loop.settings_invitation_review
```

The explicit review settings **force local console**, regardless of SMTP env.
Two Rowan aliases and Avery across two projects produce two local messages to
synthetic `example.com` primary addresses. The second command prints `skipped: 2`
without messages. Seeds never reset existing delivery states or snapshot membership.
Use `.env.issue1` instead of `.env` for the existing isolated review database.
Seeded users are invitation-only fixtures; this does not provision login credentials.

Command JSON reports sent/skipped/failed/ambiguous/withheld plus a content-free code.
`withheld` includes unresolved account lookups as well as unresolved principal
contacts, so it is not a disclosed natural-person response count. These are operator
counts, not product report fields. No addresses, participant list, response content
or raw exception diagnostics appear in the summary.

Production email configuration is environment-driven: `EMAIL_BACKEND`, `EMAIL_HOST`,
`EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`,
`DEFAULT_FROM_EMAIL`, and `INVITATION_ORIGIN`. `EMAIL_FILE_PATH` is for the file
backend. Origin accepts only a bare HTTP(S) origin, no credentials, path, query or
fragment. Use HTTPS with production settings and authenticated entry; production
configuration/delivery is #42, not authorized by local verification here.

Tests use locmem/custom synthetic transports only:
`uv run --env-file .env.issue1 pytest --postgres signal_loop/invitations/tests`.
