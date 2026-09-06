# Membership model lifecycle

`Organisation` owns projects and `OrganisationMembership` records linking the
existing Django user to an organisation. `ProjectMembership` links exactly one
organisation membership to one project in that same organisation. Both membership
types have explicit `member` / `manager` roles. Organisation manager status never
automatically grants project membership or project manager authority. Request
authorization belongs to #9; these services are not authorization endpoints.

Use normal model `save()` / `objects.create()` or `services.py` mutations.
Every save invokes full model validation, including role choices, immutable
associations and cross-organisation checks. ModelForms use the same validation.
Database uniqueness and role check constraints also protect concurrent duplicate
writes. QuerySet update/bulk_create/bulk_update/delete are deliberately rejected;
raw SQL, base Model.save and save_base are not supported application write APIs.
Database cross-table equality is enforced by validated writes, not a PostgreSQL
CHECK constraint. Direct SQL maintenance must not bypass these invariants.

Project organisation and membership user/organisation/project associations cannot
be reassigned after creation. Remove membership by setting `is_active=False`;
reactivate the existing record to return (uniqueness includes inactive records).
Change role through validated save or `change_membership`. Normal hard deletion
is rejected and parent/user foreign keys are protected. Deactivating an organisation
or organisation membership leaves child rows intact; eligibility/authorization
must require all ancestors and the user to be active, not only the project row.
No role change/removal rewrites past eligibility snapshots (#12) or touches
anonymous feedback, which must never link back to these identity-side records.

Database tests use Django's built-in temporary database lifecycle with pytest,
without an additional test dependency. Against disposable local services:

```powershell
uv run --env-file .env python manage.py migrate --noinput
uv run --env-file .env python manage.py check
uv run --env-file .env pytest --postgres signal_loop/membership/tests
uv run --env-file .env pytest --postgres
```

The database user needs CREATEDB for Django's temporary `test_` database, which is
dropped after the suite. Never point this command at production. CI uses this full
mode; `uv run pytest` keeps service-free tests available and explicitly skips the
database tests. Redis is required by management-command readiness checks; model
tests use PostgreSQL only. Missing configured PostgreSQL fails full mode rather
than silently skipping it.
