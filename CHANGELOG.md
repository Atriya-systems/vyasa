# CHANGELOG

All notable changes to the AspireACE ModelOps + ContentOps Factory.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) +
[SemVer](https://semver.org/) (major.minor.patch).

---

## [Unreleased] — v1.0.0 (in progress)

**Milestone:** M1 — Foundation + Phase 1 hardening.
**Status:** in progress.
**Session:** 2026-05-25 (start).

### Added

- **HANDOFF.md** — canonical entry doc for any future agent or operator picking up the factory.
- **ARCHITECTURE.md** — full system architecture across all 4 phases, module layout, data flow per chapter, phase deltas, key non-obvious decisions, explicit non-goals.
- **PHASE_ROADMAP.md** — Phase 1-4 scopes, transition triggers, M1-M4 milestone plan, decision matrix for transitioning, anti-pattern note on skipping phases.
- **OPERATING_GUIDE.md** — fresh-machine setup walkthrough, weekly workflow, teacher onboarding, common operations, configuration knobs, capacity math, troubleshooting.
- **ELITE_BAR.md** — 10-row quality standard applied to the factory itself; anti-patterns identified from v0.3.0 baseline; above-the-bar guidance.
- **CHANGELOG.md** — this file.

### Planned (this session)

- 7 critical bug fixes from the v0.3.0 baseline code review.
- Core infrastructure: structured logging (`utils/logging.py`), error enums (`utils/errors.py`), retry/backoff (`providers/retry.py`), lockfile (`pipeline/lockfile.py`), token-budget guard (`providers/token_budget.py`).
- Multi-subject support: `prompts/subjects/{chemistry,biology,mathematics}/` overrides + 6-8 anchor examples.
- Real test coverage: per-module unit tests + 4 subject integration tests.
- Hardened config: `pyproject.toml` (mypy/ruff/pytest), `requirements-core.txt` (verified version pins), `.gitignore` (runs/locks/db), `.env.example` (all-phases settings).
- M1 close commit + HANDOFF refresh pointing to M2.

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
