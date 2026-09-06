# Server authorization matrix

Permissions are scoped to active organisation/project context. Organisation
administrators are `OrganisationMembership.role=manager`; they are not a new
global role. All ancestor organisation/membership/project records and the user
must be active. Django staff/superuser flags grant no application permissions.

| Role in requested context | Organisation administration | Current check-in | Team report | Manager report | Publish commitment | Raw feedback |
| --- | --- | --- | --- | --- | --- | --- |
| Anonymous/inactive/removed membership | No | No | No | No | No | No |
| Organisation member without project membership | No | No | No | No | No | No |
| Project member | No | Yes | Yes | No | No | No |
| Project manager | No | Yes | Yes | Yes | Yes | No |
| Organisation administrator without project membership | Yes | No | No | No | No | No |
| Organisation administrator with project membership | Yes | According to explicit project role | According to explicit project role | Only project manager | Only project manager | No |
| Staff/superuser without memberships | No | No | No | No | No | No |

Roles combine only within the requested organisation/project. A Cedar manager
who is a Birch member cannot read Birch manager reports or publish commitments.
Membership in another organisation grants nothing. Raw feedback is denied to
every application role, including combined administrator/manager/superuser.
Infrastructure operator capabilities remain the separate policy #4/#42 risk;
these helpers do not authorize that access.

Use `has_permission(user, Permission..., organisation_id=..., project_id=...)`
in service/selectors and `@require_permission(Permission...)` around views.
Context IDs are positive integer database keys; missing, malformed, unknown or
cross-organisation project context is denied. Organisation administration accepts
an organisation ID and no project ID. Unknown permissions deny by default.

Decorated views take named URL kwargs `organisation_id` and, for project actions,
`project_id`. Authorize the resolved URL context, never a hidden form/query/HTMX
parameter. The underlying operation must use that same authorized context and
scope all object selectors to it; helpers do not authorize arbitrary object IDs
inside a payload. Recheck within a mutation transaction if role revocation can
race the write. Later feature services own window-open checks, admission,
publication privacy gates and CSRF/method requirements in addition to this
permission gate. `CURRENT_CHECK_IN` is role permission, not proof a week is open.

Unauthenticated requests redirect to the #8 login preserving local next, including
HTMX and POST. Authenticated denials always return the same plain 404 `Not found.`
with no protected payload or distinguishable existence reason, even in DEBUG.
No HTML/HTMX or HTTP-method bypass exists. CSRF middleware still independently
rejects invalid state-changing requests; these permissions never disable it.
Navigation visibility may reuse the helper but does not replace view/service
enforcement. Tests use a test-only URLconf with protected probe views so no feature
report/publishing endpoints are introduced ahead of their issues.
