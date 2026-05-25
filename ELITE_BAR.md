# ELITE BAR — quality standard applied to the factory itself

**Purpose:** Mirror of AspireACE's `ELITE_ENGINE_BAR.md` 10-row standard, but applied to each module / subsystem of this factory. Every code change in this folder is expected to pass these 10 rows (or document why it's deferred).

**Bar:** all 10 rows pass + above-the-bar judgement applied. "Elite" means using the superior approach the domain warrants, going above the stated approach when a cleaner method or hardening opportunity is visible, and doing more than asked when it makes the system more robust.

---

## The 10 rows

A factory module (e.g. `pipeline/lane_generation.py`, `providers/llm.py`, `validators/rights_validator.py`, `api/routes/generate.py`) is **elite** only when all 10 of these pass:

| # | Row | Pass means |
|---:|---|---|
| 1 | **Algorithm** | The module uses the correct approach for its domain (e.g. TF-IDF cosine for source-similarity is fine; if accuracy matters more, sentence-embedding cosine is better). Not just any working implementation — the right one. |
| 2 | **Persistence** | Stateful data is written to durable storage in a defined format (JSONL, SQLite, manifest with SHA-256). No "in-memory only" state for anything that matters across runs. Persistence is observable (you can read the file and understand what happened). |
| 3 | **Provider wiring** | Module operates correctly against both `PROVIDER=lmstudio` AND `PROVIDER=openai`. Never hardcodes one. Schemas degrade gracefully if `response_format=json_schema` isn't supported. |
| 4 | **Operator surface** | There's a way for an operator (you, a teacher, future agent) to invoke / observe / debug this module from the CLI or Streamlit. No code paths that only get exercised by tests. |
| 5 | **Telemetry** | Module emits structured logs (`utils/logging.py`) with correlation IDs (run_id + record_id where applicable). Per-call latency tracked. Failures logged with full context, not swallowed. |
| 6 | **Performance** | SLA stated in the module's docstring (e.g. "verify one lane of 100 records in <60s on Qwen3-8B Q4_K_M"). Measured. Regressions caught by tests. |
| 7 | **Failure modes** | Module declares its `degraded_reason` enum values (`utils/errors.py`). Every error path routes to one of those. No bare `except Exception`. No silent swallows. |
| 8 | **Tests** | Real unit tests covering happy path + at least 2 failure paths. Integration test that exercises the module in a realistic pipeline run. Test names describe behavior, not implementation. |
| 9 | **Operationally verified** | Module has been exercised end-to-end on real teacher source material at least once. Not just synthetic fixtures. |
| 10 | **Provenance** | Module's purpose, version, owner, and SLA stated in its docstring. CHANGELOG entry exists for any change. README or docs/* reference if it's user-facing. |

---

## Above the bar — what "elite" really means

Passing 10/10 is the floor. Above-the-bar work means:

- **Use the superior algorithm the domain warrants.** TF-IDF cosine works for similarity; sentence-embeddings are better. Rule-based bad-phrase detection works; LLM-judge with calibrated thresholds is better. Pick the right one for the stakes.
- **Go above the stated approach when a cleaner method, missing observability, adjacent bug, or hardening opportunity is visible — handle it in the same pass.** If you're touching `validators/basic_checks.py` to add a bad-phrase, and you notice the function has a single-string-match heuristic that misses LLM-self-reference patterns, expand the heuristic in the same change. Don't leave the obvious gap for "next time."
- **Do more than asked when it makes the system more robust / elite.** Add the index. Add the structured `degraded_reason`. Add the lockfile. Add the run-stats logging. Add the README. Most of these are 10-minute extras that compound over months.

---

## Anti-patterns that fail the bar

These are real shapes seen in the v0.3.0 baseline that the M1 hardening pass fixes. Don't reintroduce:

| Anti-pattern | Where (v0.3.0) | Why it fails |
|---|---|---|
| Bare `except Exception` swallow with no logging | `providers/llm.py:36-40` | Fails row 5 (telemetry) + row 7 (failure modes). Original error is lost; operator has no way to know schema validation was disabled. |
| Aggregate gate logic on per-record rules | `pipeline/runner.py:47-49` | Fails row 7 (failure modes). Lets training-disallowed sources through if any other lane is allowed. |
| String-substring routing on error codes | `pipeline/verify.py:75` | Fails row 7. Rename the error string and routing breaks silently. |
| In-memory dict for legally-important state | `review_app/app.py` approval action | Fails row 2 (persistence) + row 7. Approver identity / timestamp / reason not durably logged. |
| Trivial tests as proof of correctness | `tests/test_json_schemas_load.py` (7 lines, loads files) | Fails row 8. "It parses" is not a test. |
| Plumbed-but-never-called integration | `tracking/mlflow_logger.py` | Fails row 4 (operator surface) + row 10 (provenance — claims to track but never runs). |
| Stub file with misleading name | `rag/build_embeddings_manifest.py` (writes manifest, doesn't embed) | Fails row 10. Filename promises a thing the code doesn't do. |
| Single-example anchor | `examples/sample_owned_source.json` (one Physics paragraph) | Fails row 9 (operationally verified). Doesn't exercise Chem/Bio/Maths shapes. |

---

## Above-the-bar examples (what we ARE doing in M1)

- **Bug fix #6 (audit trail):** founder asked for a fix to the weak audit trail. Going above the bar: redesign the Streamlit approve action to write an append-only audit log with (record_id, approver_id, approver_role, decision, reason, timestamp, source_unit_id, lane), plus add a per-teacher approval-rate dashboard so the rate of approvals can be monitored over time.
- **Bug fix #5 (prompt array shape):** founder asked to fix the prompt example. Going above the bar: add a `prompts/README.md` documenting the prompt taxonomy + versioning policy, and add a schema-shape integration test that runs each prompt against a mock LLM and verifies the output matches the lane's schema.
- **Multi-subject support:** founder asked for Chem/Bio/Maths prompts. Going above the bar: add `prompts/subjects/<subject>/` overrides, per-subject anchor examples, per-subject `unit_type` enum extensions, and per-subject smoke tests that prove a chapter from each subject runs end-to-end.

---

## How to apply this bar to a new module

When you add or significantly modify a module:

1. Open the module's docstring. State:
   - Purpose (one sentence)
   - Version + author + date
   - SLA (latency / throughput target)
   - Inputs / outputs / failure modes (link to `utils/errors.py` enums)
2. Cover all 10 rows above. If any row is genuinely N/A, state why in the docstring.
3. Write the tests (`tests/unit/test_<module>.py`) — happy + 2 failure paths minimum.
4. If the module is operator-facing, add a CLI command or Streamlit hook or `tools/*.py` wrapper.
5. Emit structured logs from key code paths.
6. Add a CHANGELOG.md entry under the next-version section.
7. Run `pytest -v` to confirm green.
8. Update docs/* if user-facing behavior changes.

---

## When the bar can be deferred

Rarely — only when:

- The module is explicitly marked `[phase:N]` for a later phase (e.g. `api/routes/admin.py` is Phase 4; we won't write Phase 4 tests in M1).
- The module is a deliberate stub for future implementation, clearly marked at the top of the file:
  ```python
  """[STUB — Phase N] This module's full implementation lands in M<N>.

  Current state: skeleton + signature. No production callers.
  """
  ```
- Founder explicitly defers via a memory note or in-chat direction.

Any deferral is logged in CHANGELOG.md with rationale.

---

*Update this file when the bar itself changes (new row, retired row, threshold shifts). Not for every code edit.*
