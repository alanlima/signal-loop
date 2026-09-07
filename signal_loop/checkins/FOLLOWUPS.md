# Fixed follow-up service (#19)

`followups.reserve_followups(projects, remaining_budget=..., deadline=...,
store=..., clock=...)` freezes an allocation. Each project is an exact object with
`project` (opaque ID string), `week` (local Monday), `project_name`, and `answers`
(required J1/J2, optional J3). Supply 0-3 selected, authorized projects in the
already-frozen journey order. The caller owns authorization; this pure service
does not read membership or accept a participant-selected replacement scope.

Selection uses only J1/J2: blocked/F1 priority 1; overloaded/F2 priority 2;
at_risk/F1 priority 3; stretched/F2 priority 4. Choose the lowest per project,
then sort by priority and frozen order. Reserve at most the first two, bounded
by the supplied remaining global budget. Declined/unknown/ordinary answers do
not invent a candidate. Even an empty first allocation is frozen; later edits
cannot replenish it. Budget must be integer 0-2 (not bool); invalid input, zero
budget or elapsed allowance returns an empty tuple without an AI call.

Call `select_followup(slot, store=..., adapter=..., deadline=..., clock=...)`
for each returned reserved slot. It returns `Decision` with `shown`, `no_question`
or `unavailable`; only `shown` includes a fixed catalog question ID/text. There
is no generated answer. Render this plain text with normal Django escaping.
The UI should allow continuation for either no-question result. No form, view,
clock model, persistence wiring or final-feedback path is added in this issue.

The provider receives only one project/local week, privacy version, reserved F1/F2,
and delivery/workload enums through #18. J3 is accepted as bounded feedback data
but completely omitted from the provider request, as are project display names,
P1-P5, identities, credentials, other project narratives, timing and budget.
Instructions inside J3 cannot change ranking, scope, catalog text or slot count.
Unknown fields and invalid enum/text values fail before allocation. Output is
validated by #18; the service formats only its own catalog. A wrong ID/project,
invented prompt, malformed response, timeout or provider error yields no question.

`Adapter.follow_up(..., time_allowance=remaining_seconds)` now allows a stricter
per-call deadline. It cannot increase #18's configured deadline or permit a retry.
The service caps each call at min(2 seconds, remaining journey allowance), rechecks
the authoritative clock after the claim and after the result, and ignores late
success. An expired reserved slot is closed without a provider call. Suppressed,
failed, expired and shown slots all remain spent; a third project cannot replace
one. Final eligibility after answer edits, excluded-answer acknowledgement and
the 600-second finish view remain #20 responsibilities.

## Durable handoff to #20

The required `AllocationStore` protocol separates one journey's private slot state
from this pure selector. There is deliberately no default store and no ORM link
to submitted feedback. `FakeAllocationStore` is an in-memory, lock-protected test
fixture only. It demonstrates contract behavior; restarting it would lose state,
so it must never be used for a real browser journey.

The #20 implementation must bind the store to the existing private draft and:

1. Atomically `reserve_once` the entire first allocation (including empty) before
   any provider request. Subsequent calls return that allocation without changing
   projects, questions or triggering enums. The unused adaptive slots close.
2. Atomically `claim` the exact reserved slot once, committing before AI. Concurrent
   tabs must have one winner. The budget is consumed at reservation; the later
   selection phase evaluates those already-reserved slots, not new free slots.
3. Persist `record(slot, decision)` before the service exposes a shown question.
   A claim whose call/process/save fails must remain spent. On resume, a claim
   without a completed outcome closes safely; it must never be reclaimed or retried.
4. Keep this state and any shown answer only in the expiring private draft, cascade
   it on discard/submission/expiry, and never export allocation metadata to feedback.
5. Supply the original authoritative deadline min(start + 600 seconds, draft expiry)
   on every request. New calls/refresh/back must not reset it. Close pending/unseen
   slots at the finish boundary and use persisted shown questions for review.

Tests cover all priorities/ties, one/two/three and ordinary projects, exhausted
budget, deadline/late output, exact provider context, injection/unknown fields,
fixed catalog and safe fake failure modes, immutable empty/spent allocation,
concurrent claims, forged slots and failed result persistence. The real #18 fake
transport sleeping 10 seconds is cancelled when only 0.4 seconds remain.

```powershell
uv run pytest signal_loop/checkins/tests/test_followups.py signal_loop/ai/tests
uv run --env-file .env.issue1 pytest --postgres
```

No new dependency or live provider is used. #20 must supply the durable store
before integrating this service into the check-in route.

