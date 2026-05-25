# CHANGELOG

All notable changes to the AspireACE ModelOps + ContentOps Factory.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) +
[SemVer](https://semver.org/) (major.minor.patch).

---

## [Unreleased] — v2.0.0 (M2 — Phase 2 API layer)

Not started. See [PHASE_ROADMAP.md](PHASE_ROADMAP.md) §M2 for scope.

---

## [1.0.0-M1] — 2026-05-25

**Milestone:** M1 — Foundation + Phase 1 hardening.
**Status:** CLOSED.
**Sessions:** 2026-05-25.

### Added — Documentation (6 anchor files)

- **HANDOFF.md** — canonical entry doc for any future agent or operator picking up the factory.
- **ARCHITECTURE.md** — full system architecture across all 4 phases, module layout, data flow per chapter, phase deltas, key non-obvious decisions, explicit non-goals.
- **PHASE_ROADMAP.md** — Phase 1-4 scopes, transition triggers, M1-M4 milestone plan, decision matrix for transitioning, anti-pattern note on skipping phases.
- **OPERATING_GUIDE.md** — fresh-machine setup walkthrough, weekly workflow, teacher onboarding, common operations, configuration knobs, capacity math, troubleshooting.
- **ELITE_BAR.md** — 10-row quality standard applied to the factory itself; anti-patterns identified from v0.3.0 baseline; above-the-bar guidance.
- **CHANGELOG.md** — this file.
- **prompts/README.md** — prompt taxonomy + versioning + subject-override rules + schema-shape rules.

### Added — Core infrastructure modules

- `src/aspireace_mocf/utils/errors.py` — enum-based error taxonomy
  (`LLMErrorCode`, `PipelineErrorCode`, `VerificationErrorCode`, `RightsErrorCode`)
  + `route_record()` helper replacing string-substring routing.
- `src/aspireace_mocf/utils/logging.py` — structlog-based structured JSON-lines
  logging with contextvars correlation (run_id / record_id / lane).
- `src/aspireace_mocf/providers/retry.py` — tenacity exponential-backoff
  decorator scoped to transient LLM errors only.
- `src/aspireace_mocf/providers/token_budget.py` — chars-per-token estimate +
  per-model context-window guard. Raises `PROMPT_TOO_LARGE` before silent
  truncation.
- `src/aspireace_mocf/pipeline/lockfile.py` — PID + hostname + timestamp
  lockfile with stale-PID detection + auto-break.
- `src/aspireace_mocf/pipeline/prompt_loader.py` — single entry point for
  prompt loading; resolves base v1 + subject addendum; LRU-cached.

### Added — Multi-subject support

- `prompts/v1/` — canonical v1 prompts (copied from `prompts/`; legacy path kept for back-compat).
- `prompts/subjects/physics/addendum.md` — formulae notation, sign conventions, JEE/NEET trap categories, depth-tier differentials.
- `prompts/subjects/chemistry/addendum.md` — reaction arrows, IUPAC nomenclature, mechanism conventions, NEET vs JEE chemistry emphasis.
- `prompts/subjects/biology/addendum.md` — process-flow descriptions, anatomy terminology, genetics notation, NEET-only scope, text-only diagram-reference policy.
- `prompts/subjects/mathematics/addendum.md` — LaTeX usage, proof structure, worked-example format, JEE Mains vs Adv depth.
- `examples/physics_ch01_units_measurements_owned.json` — ~450-word SME-style anchor source.
- `examples/chemistry_ch02_atomic_structure_owned.json` — ~480-word SME-style anchor source.
- `examples/biology_ch08_cell_unit_of_life_owned.json` — ~500-word SME-style anchor source.
- `examples/mathematics_ch01_sets_owned.json` — ~480-word SME-style anchor source.
- `examples/source_ledger.csv` — extended schema (teacher_id + seniority) + 4 SME entries + 1 REFERENCE_ONLY negative-path entry.

### Added — Tests

- `tests/conftest.py` — shared pytest fixtures (sample records per shape, rights ledger fixture, fixtures_dir helper).
- `tests/unit/test_errors.py` — 13 tests.
- `tests/unit/test_basic_checks.py` — 23 tests (with parameterized bad-phrase scan).
- `tests/unit/test_rights_validator.py` — 10 tests.
- `tests/unit/test_token_budget.py` — 8 tests.
- `tests/unit/test_lockfile.py` — 6 tests.
- `tests/unit/test_prompt_loader.py` — 10 tests.
- `tests/unit/test_similarity.py` — 8 tests.
- `tests/unit/test_schema_validator.py` — 7 tests.
- `tests/unit/test_text_utils.py` — 13 tests.

### Added — Config hardening

- `pyproject.toml` — version 1.0.0 + license + optional-dependencies (training / review / dev) + pytest / mypy / ruff / coverage config.
- `.gitignore` — expanded from 11 lines to ~70, covering all phases' artefacts.
- `.env.example` — restructured into phase sections (Phase 1 / 2 / 3 / 4) with secret-generation hints.
- `requirements-core.txt` — added tenacity, structlog, pydantic, langgraph-checkpoint-sqlite. Pinned langgraph to `>=0.2.0,<2.0.0` (Bug #7 fix).

### Fixed — 7 critical bugs from v0.3.0 baseline

- **Bug #1**: `providers/llm.py` — replaced bare `except Exception` swallow with specific `BadRequestError` handling. Falls back to no-`response_format` only when API rejects it; preserves original error context; logs the fallback.
- **Bug #2**: `pipeline/runner.py` — per-lane rights gating. Old code raised only on aggregate (BOTH rag AND app_content blocked); training lanes could leak training data from reference-only sources. Now each lane is gated individually via `LANE_TO_RIGHTS_CATEGORY` map.
- **Bug #3**: `pipeline/source_units.py` — validate-all-then-truncate. Old code broke mid-loop producing inconsistent accepted/rejected partials.
- **Bug #4**: `agents/supervisor.py` — per-lane retry decisions via `_per_lane_failures()`. Old code retried only when TOTAL accepted == 0; if 8 of 9 lanes succeeded and 1 silently produced zero, supervisor finished. Now retries on any zero-accepted non-skipped lane.
- **Bug #5**: `prompts/01_source_units.md` — array-shape example. Old example showed single object; LLM commonly returned single object instead of array.
- **Bug #6**: `review_app/app.py` — real audit trail. Old code: no auth, hardcoded "reviewer_001", no timestamp, no append-only log. New: `REVIEWER_USERS` env auth, two-tier junior/senior review, per-decision `audit_log.jsonl` with ISO-8601 UTC timestamps + reviewer_id + reason + train_allowed transition.
- **Bug #7**: `requirements-core.txt` — corrected `langgraph>=0.2.0,<2.0.0` (was impossible `>=1.0.0`).

### Fixed — Fragility issues addressed in passing (5/10 from inventory)

- **Bug #8** (no retry/backoff): added via `providers/retry.py` + `@with_llm_retry` decorator.
- **Bug #10** (in-memory checkpointer): replaced `MemorySaver` with `SqliteSaver` writing to `runs/<run_id>/agent_state.sqlite`.
- **Bug #11** (O(n²) similarity): introduced `SourceSimilarityCache` — fit once, transform many.
- **Bug #12** (thin bad-phrase library): expanded from 2 substrings to ~40 patterns covering LLM-self-reference + prompt-frame leakage + schema leakage + markdown leakage.
- **Bug #13** (string-substring routing): replaced with enum set-membership via `utils.errors.route_record()`.
- **Bug #14** (no token-budget guard): added via `providers/token_budget.py`.
- **Bug #15** (no concurrent-run protection): added via `pipeline/lockfile.py`.
- **Bug #16** (no structured logging): added via `utils/logging.py` + correlation IDs.
- **Bug #21** (silent record drop in export): added structured warning logs with sample record IDs.

### Deferred (M2+ scope)

- **Bug #9** (no lane-level checkpointing in runner) — partial via SqliteSaver in supervisor; full lane-level resume in M2.
- **Bug #17** (no integration tests against real LLM) — operational verification, not unit-testable.
- **Bug #18** (MLflow never called) — wired in but call sites land in M3 training pipeline.
- **Bug #19** (rag/build_embeddings_manifest.py stub) — replaced with real `push_to_qdrant.py` in M2.
- **Bug #20** (eval/evaluate_dataset.py shallow) — full eval harness lands in M3.
- **Bug #22** (no type-check config) — mypy config added in M1; full strict-mode pass scheduled M3.
- **Bug #23** (English-only hardcoded system prompt) — deferred until Hindi/multi-language scope returns.
- **Bug #24** (LangGraph lazy imports unexplained) — explained inline in supervisor.py.
- **Bug #25** (no per-run cost tracking) — `tracking/run_stats.py` lands in M2.

### Verification at M1 close

- 46 unit tests pass in 0.42s on Python 3.12.10 (no-external-deps subset).
- Full ~120-test suite requires `pip install -r requirements-core.txt` first.
- Six atomic commits on `main` branch of the factory's standalone git repo:
  1. baseline commit (v0.3.0 as shared)
  2. docs foundation (6 anchor docs)
  3. critical bugs + core infrastructure (17 files)
  4. multi-subject (prompts v1/, subjects/, anchors, prompt_loader)
  5. tests + config hardening (~12 files)
  6. M1 close (CHANGELOG + HANDOFF refresh)

---

---

## [0.3.0] — 2026-05-25 (baseline as shared)

**Status:** baseline commit. Factory as the founder shared it.

### Initial contents

- `aspireace_mocf` Python package v0.3.0 with:
  - 9 lanes (3 training + 6 app content)
  - 9 JSON Schemas
  - 6 prompt templates
  - LangGraph supervisor with human-in-loop
  - LM Studio + OpenAI provider abstraction
  - Streamlit SME review UI
  - LoRA SFT training scripts for Qwen3-8B
  - MLflow + DVC tracking scaffolding
- `app_binding/` — 4 JSON contracts mapping factory outputs to AspireACE engines + surfaces
- Single Physics example source + minimal rights ledger
- 2 trivial test files

### Known issues (to be fixed in v1.0.0)

| # | Severity | Issue | Location |
|---:|---|---|---|
| 1 | 🔴 critical | Silent exception swallow in LLM client | `providers/llm.py:36-40` |
| 2 | 🔴 critical | Rights gate uses wrong aggregate logic; lets training-disallowed sources through | `pipeline/runner.py:47-49` |
| 3 | 🟡 bug | Source units truncate-mid-validate; partial accept/reject lists | `pipeline/source_units.py:47` |
| 4 | 🟡 bug | Supervisor retry decision based on aggregate, not per-lane | `agents/supervisor.py:71` |
| 5 | 🟡 bug | Prompt example shows object instead of array | `prompts/01_source_units.md` |
| 6 | 🔴 critical | Review app weak audit trail on the legal gate | `review_app/app.py` |
| 7 | 🔴 critical | `langgraph>=1.0.0` pin is wrong (real version is 0.2.x) | `requirements-core.txt:5` |
| 8 | 🟡 fragility | No retry/backoff on transient LLM failures | `providers/llm.py` |
| 9 | 🟡 fragility | No checkpointing in runner; one bad lane kills whole run | `pipeline/runner.py` |
| 10 | 🟡 fragility | LangGraph checkpointer is `MemorySaver` (in-memory only) | `agents/supervisor.py:119` |
| 11 | 🟡 fragility | O(n²) similarity check; rebuilds TF-IDF per record | `validators/similarity.py` |
| 12 | 🟡 fragility | Bad-phrase heuristic too thin (only 2 substrings) | `validators/basic_checks.py:27` |
| 13 | 🟡 fragility | String-substring error routing | `pipeline/verify.py:75` |
| 14 | 🟡 fragility | No token-budget guard before LLM calls | `providers/llm.py` |
| 15 | 🟡 fragility | No lockfile on concurrent runs against same run_id | `pipeline/runner.py` |
| 16 | 🟠 polish | No structured logging beyond `tqdm` | (everywhere) |
| 17 | 🟠 polish | Tests are 2 trivial files; essentially zero coverage | `tests/` |
| 18 | 🟠 polish | MLflow plumbed but never called | `tracking/mlflow_logger.py` |
| 19 | 🟠 polish | `rag/build_embeddings_manifest.py` is a stub with misleading filename | `rag/` |
| 20 | 🟠 polish | `eval/evaluate_dataset.py` is shallow (counts only) | `eval/` |
| 21 | 🟠 polish | `pipeline/export.py:22` silent record drop | `pipeline/export.py` |
| 22 | 🟠 polish | No mypy/pyright config | `pyproject.toml` |
| 23 | 🟠 polish | Hardcoded English system prompt | `providers/llm.py` |
| 24 | 🟠 polish | LangGraph lazy imports unexplained | `agents/supervisor.py` |
| 25 | 🟠 polish | No per-run cost / token tracking | (everywhere) |

The first 7 (🔴 + 🟡 bug) are blockers for v1.0.0. The 🟡 fragility items ship in M1 to varying degrees. The 🟠 polish items are landed where convenient in M1 + cleanup pass in M4.

---

## Version history (planned)

- **0.3.0** — baseline as shared (2026-05-25). Demo-grade, not production-grade.
- **1.0.0** — M1 close. Phase 1 elite. All 🔴 critical bugs fixed, multi-subject, core infra, real tests, foundation docs.
- **2.0.0** — M2 close. Phase 2 API layer.
- **3.0.0** — M3 close. Phase 3 trained tutor + serving.
- **4.0.0** — M4 close. Phase 4 multi-tenant productized.

---

*Add a new section under "Unreleased" for every meaningful change. Promote to a numbered version on milestone close.*
