# AI adapter (#18)

`Adapter.follow_up(request)` and `Adapter.structured_analysis(request, scope=scope)`
return `Result(candidate=..., failure=None, attempts=N)` or a content-free `Failure`
enum with no candidate. Candidate contents are excluded from the result repr.
No ORM, HTTP endpoint, production provider, credential setting or dependency is
introduced. Callers must never serialize this restricted result into a view.

The structured request has exactly `schema: analysis-request/1.0`,
`output_schema`, and `inputs` (1-100 complete restricted artifacts).
Supported output schemas are the exact #6 themes, trends, issues, evidence,
recommendations, manager-report and team-summary `1.0` contracts. Inputs support
those plus canonical `feedback/1.0`; there is no J-field persistence substitute.
Every input/output uses the full E envelope and data from
[_docs/analysis-contracts.md](../../_docs/analysis-contracts.md). Both sides reject
unknown nested fields, null optional values, bool-as-int, unsupported versions,
non-Monday weeks, duplicate IDs/references and malformed/duplicate-key JSON.
Text must already have normalized LF; adapters never trim or truncate it.

The caller supplies a trusted `Scope` with project, local week, actual UTC window
close, current time, and restricted reference metadata (kind, project/week,
expiry). This is local validator context, **not provider input**, and contains no
identity map. Scope/expiry checks apply to every reference and provenance input.
Only the expressly declared preceding aggregate of a consecutive trend can refer
to a prior week. Output cannot outlive any request input or referenced source, or
14 days after the window closes. Request inputs are current-scope artifacts;
the future aggregate owner must supply its reviewed contract before sending new
aggregate payload types. Existing prior aggregate references can be validated.

Validation order is shape/enums, local invariants, then reference resolution.
This boundary establishes syntactic and scoped-reference validity only. It does
**not** establish natural-person distinct counts, grounding, current/previous
roster safety, or privacy. Model counts and booleans remain untrusted claims.
False safety candidates remain restricted for downstream rejection; true values
give no release authority. #25-#32 independently verify semantic claims; reporting
owns the release gate. AI requests cannot ask for release-control or audience-release
output. The explicit synthetic fixture registry in the tests is never a real
distinctness proof or default production context.

Follow-up transport is deliberately separate because #6 defines the stored
follow-up answer, while #5 defines the prior catalog decision. Exactly:

```python
request = {
    "schema": "followup-request/1.0", "project": "cedar", "week": "2026-09-07",
    "privacy_policy": "1.0", "question": "F1",
    "data": {"delivery": "blocked", "workload": "manageable", "note": "Synthetic delay."},
}
# response: same project/week/privacy_policy/question, schema followup-response/1.0,
# and decision "show" or "suppress". No prompt text, answer, source or identity.
```

`note` is optional 0-320; enums and eligibility match #5. #19 must reserve one
catalog slot before calling, enforce the global budget and render the catalog's
fixed escaped question text. AI can only suppress that slot. No personal P1-P5,
other project, budget, journey, admission secret or generated prompt is accepted.
Shown/skipped/failed slots cannot be called again by navigation/retry. That durable
allocation is the caller's responsibility; this stateless adapter cannot infer it.

## Execution and configuration

```python
from signal_loop.ai.adapter import Adapter, Configuration, Limits
from signal_loop.ai.fake import FakeProvider

adapter = Adapter(FakeProvider(), Configuration(
    followup_model="synthetic-followup-v1",
    analysis_model="synthetic-analysis-v1",
    followup=Limits(timeout=2, total_timeout=2, max_attempts=1),
    analysis=Limits(timeout=5, total_timeout=10, max_attempts=2),
))
result = adapter.follow_up(request)
# A caller may shorten the existing cap for a nearly elapsed journey:
# result = adapter.follow_up(request, time_allowance=0.5)
```

Defaults above are explicit seconds/total attempts, including the first attempt.
Limits accept finite positive times up to 60 seconds and 1-5 attempts; follow-up
always permits only one attempt and a total no greater than two seconds. The
shared monotonic deadline includes spawn and all attempts; retries cannot multiply
it. No backoff sleep is added. Timeout/unavailability are retryable only within
both limits. Invalid input/output, permanent rejection and unexpected internal
errors stop immediately. Exhausting multiple transient attempts returns
`retries_exhausted`; reaching the deadline returns `timeout`. Late output is ignored.

Providers implement spawn-picklable `invoke(operation, model, request, attempt)`
and return JSON text. Calls execute in disposable daemon processes; the parent
polls with its deadline, then terminates and joins the worker. Cleanup has two
bounded 100ms join allowances (termination then kill), not an unbounded executor
shutdown. OS scheduling/cleanup can delay returning the failure slightly beyond
the decision deadline; no late result is accepted. There are no abandoned executor
threads. Trusted provider wrappers must not spawn subprocesses or persist inputs.
The adapter sends only the minimized request, never Scope reference context.
Processes are a cancellation boundary, not a sandbox against hostile provider code.

Worker stdout/stderr are redirected to the null device before provider invocation.
Exceptions become fixed enums, never str/repr or tracebacks. No application logger
is called. Encoded requests and provider responses are capped at 1MB; duplicate
input source/item IDs are rejected before a call. #39 owns a future vendor
wrapper and its provider-side timeout/zero-retention verification; vendor imports
belong exclusively in that wrapper, and no production egress is enabled here.
Future credentials must be injected separately, never embedded in model IDs,
fixture values, error messages or configuration committed to source control.

## Deterministic fake and verification

`FakeProvider(response=complete_artifact, script=("unavailable", "valid"))`
returns the same artifact on the second attempt. Scripts also support `timeout`,
`rejected`, `malformed`, `error`, `suppress` and repeated exhaustion (the last
script entry repeats). `delay=10` really blocks for ten seconds so tests demonstrate
parent-side termination, independently of a provider raising TimeoutError.
`raw_response` supports malformed JSON tests and is excluded from repr.
Analysis requires an explicit fixture; the fake never fabricates support from
real input. Follow-up defaults to the already-reserved question with `show`.

```powershell
uv run pytest signal_loop/ai/tests
uv run --env-file .env.issue1 pytest --postgres
uv run ruff check .
```

Contract tests assemble the exact complete E/data fixtures directly from #6,
including all eight valid/invalid examples, and exercise fake calls, nested
validation, reference/expiry failures, bounded retry counts, sleeping-worker wall
time and zero remaining child processes, and stdout/stderr/error redaction.
No live AI call is made.
