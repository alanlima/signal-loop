# MVP module architecture

Version 1.0, 2026-09-07. This is the agreed layout for future implementations, not a claim that these modules exist. Read [anonymity-policy.md](anonymity-policy.md) and [check-in-policy.md](check-in-policy.md) before using the [analysis contracts](analysis-contracts.md).

Use Django apps under `signal_loop/` with the names below. Each app owns its models/migrations, `services.py` for mutations, `selectors.py` for scoped reads, and `tests/` when introduced. Views live in the owning app's `views.py`; template paths are `templates/<app>/...`; HTMX uses the same authorization and projections as full pages. Transport contracts live in `signal_loop/contracts/`, with `feedback.py`, `analysis.py`, `reports.py`, `validation.py`, and `versions.py`; contracts contain no ORM imports.

| Module | Ownership and public boundary | Allowed outgoing dependencies |
| --- | --- | --- |
| `accounts` | Django authentication integration, sign-in/out, account lifecycle | Django auth only |
| `membership` | Organisations, projects, membership/manager roles; scoped eligibility facts | accounts |
| `authorization` | Central project/audience authorization predicates, deny by default | accounts, membership |
| `windows` | UTC project-week opening/closing, immutable window scope | membership |
| `admission` | Eligibility credentials, transient identity-side participation state, retry/admission decision; protocol remains #13 | authorization, windows, contracts |
| `checkins` | Own transient personal/project drafts, question catalog/budget, conflict-safe save, timer and finish path | authorization, windows, admission, contracts |
| `feedback` | Anonymous project-week feedback persistence, scoped restricted source access and expiry | contracts, windows; no accounts/membership/admission model imports |
| `submission` | Application orchestration of atomic redemption/persistence (#21), no durable models linking those sides | admission, feedback, contracts; narrow transaction boundary only |
| `ai` | Provider interface, deterministic fake, bounded structured output validation; no vendor choice here | contracts only |
| `analysis` | Aggregation, themes, trends, issues/severity, evidence, recommendations and privacy gates; restricted artifacts | feedback, ai, contracts; scoped membership context through authorization selector, never account/participation joins |
| `reporting` | Composition, immutable manager/team releases, joint audience review, history and withdrawal; safe selectors for views | analysis, authorization, contracts |
| `commitments` | Manager drafts/approval and independent team-safe publication gate | reporting, authorization, contracts; no feedback access |
| `pipeline` | Celery orchestration, leases, retry states/idempotency and scheduling | windows, analysis, reporting, contracts |
| `operations` | Expiry enforcement and content-free diagnostics; explicit deletion service calls | owned app deletion interfaces only; no cross-store content/identity query API |

Dependency arrows mean caller -> callee. Reverse imports and view-to-model shortcuts across apps are forbidden. Ownership of a table does not authorize every method in an importing module to read it. Identity-side apps must never call restricted feedback selectors; reporting views receive only approved audience projections. No user/project-member foreign key, shared journey/response ID or identity-side credential may cross into feedback or analysis artifacts. The submission transaction may coordinate validation and commit but must leave no durable identity-feedback join or correlated diagnostics; #13 proves the protocol before implementation.

Use PostgreSQL for durable owned data, Django templates/HTMX for UI, Celery/Redis for background delivery of opaque scoped work references. Queue messages contain no raw feedback, personal reflection, credentials or user IDs. Restrict infrastructure and database access separately from application roles as #4 requires. A module boundary alone is not a security boundary; #9/#13/#38/#42 must implement permissions, expiry, logs and operational separation.

Personal P1-P5 stay in `checkins` draft storage and never reach `submission`, `feedback`, `ai` or `analysis`. The payload presented to submission contains only substantive selected project sections, each scoped independently; no shared multi-project record survives successful submission. Input/schema validation is owned by `contracts`, eligibility by `admission`, exact-once atomic persistence by `submission`, content/support/privacy validation by `analysis`, audience authorization and immutable publication by `reporting`. A manager's commitment edit must re-enter the team release gate.

Implementation order follows these boundaries; missing components use validated synthetic fixtures at their public interface, never a bypass of privacy checks. #33 owns pipeline wiring, #18 the fake/provider adapter, #25-#32 concrete analysis/composition, #36 commitments. Contracts deliberately avoid specifying cryptography or ORM schema. No new runtime dependency or application code is introduced here.
