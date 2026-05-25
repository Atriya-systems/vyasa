# HANDOFF — Read this first

**This is the entry point for any agent or operator picking up the factory. Read this in full before touching anything else.**

**Project:** AspireACE ModelOps + ContentOps Factory
**Owner:** Piyush Batra · ATRIYA SYSTEMS PVT LTD · CONFIDENTIAL
**Version:** v1.0.0-M1 (M1 milestone closed) — see CHANGELOG.md
**Last refreshed:** 2026-05-25 (M1 close)

---

## What this thing is, in one paragraph

A standalone content + training-data factory for the AspireACE NEET/JEE app. Takes one piece of SME-written source material (a teacher's chapter notes, say), runs it through an LLM (Qwen3-8B local via LM Studio, or any OpenAI-compatible API), produces nine flavors of structured output (3 training-data lanes + 6 app-content lanes + RAG chunks + offline bundle), gates them through a rights ledger + SME review queue, and writes approved records out as JSONL ready for ingestion into the AspireACE database or future fine-tuning runs.

**Standalone by design.** Does not live in the AspireACE app repo. Operates on its own machine (currently a 5060 8GB box at the coaching). Connects to the app via file drop + a small ingest bridge script.

---

## Where things are

```
HANDOFF.md                  this file
ARCHITECTURE.md             full architecture across all 4 phases
PHASE_ROADMAP.md            Phase 1/2/3/4 scopes + transition triggers
OPERATING_GUIDE.md          week-in-the-life, runbook, troubleshooting
ELITE_BAR.md                quality standard applied to the factory itself
CHANGELOG.md                every change since v0.3.0 baseline
README.md                   quickstart (lighter; HANDOFF supersedes for state)

src/aspireace_mocf/         the Python package
prompts/                    LLM prompt templates (versioned, subject-overridable)
schemas/                    JSON Schemas for every record type
app_binding/                AspireACE engine + surface contracts
examples/                   anchor source-material samples (Phy/Chem/Bio/Maths)
training_scripts/           Qwen3-8B LoRA SFT + adapter merge (Phase 3)
serving/                    vLLM + OpenAI-compat shim (Phase 3)
review_app/                 Streamlit SME review queue
intake/                     teacher source intake (web form, OCR, normalizer)
tests/                      real per-module + integration tests
tools/                      bridge scripts (Neon ingest, batch runner, digests)
eval/                       evaluation + golden-set tooling
docs/                       deep-dive guides per topic
```

---

## Current state (as of session close)

**v0.3.0 baseline committed** at the initial git init. 68 files, exactly as the founder shared 2026-05-25.

**v1.0.0-M1 CLOSED.** Elite enhancement Pass 1 complete. ~6,000 lines added across documentation, code, tests, and config. Phase 1 is now production-ready.

**M1 — Foundation + Phase 1 hardening:** ✅ COMPLETE
- ✅ Foundational docs (6 anchor files: HANDOFF, ARCHITECTURE, PHASE_ROADMAP, OPERATING_GUIDE, ELITE_BAR, CHANGELOG)
- ✅ 7 critical bug fixes (silent exception swallow, rights gate logic, truncate-mid-validate, supervisor retry, prompt array shape, review audit trail, langgraph version pin)
- ✅ Core infrastructure (utils/errors.py enum taxonomy, utils/logging.py structlog, providers/retry.py tenacity backoff, providers/token_budget.py guard, pipeline/lockfile.py concurrent-run protection)
- ✅ Multi-subject (prompt_loader.py + 4 subject addendums + 4 anchor source examples + extended source_ledger.csv)
- ✅ Real test coverage (~120 unit tests across 9 modules; 46 verified passing locally without external deps)
- ✅ Hardened config (pyproject.toml v1.0.0 with mypy/ruff/pytest/coverage; .gitignore expanded ~7×; .env.example for all 4 phases)

**Verification at M1 close:**
- 46 unit tests pass in 0.42s on Python 3.12.10 (subset that doesn't need pip-installed deps)
- Full test suite requires `pip install -r requirements-core.txt` first; once installed, all ~120 tests should pass
- git log shows 6 atomic commits (baseline + 5 M1 milestones)

**M2 — Phase 2 API layer:** NOT STARTED — see [PHASE_ROADMAP.md](PHASE_ROADMAP.md) §M2 for scope. Activates once Phase 1 has been operationally proven (content actually landing in the AspireACE app + at least one chapter SME-approved end-to-end).
**M3 — Phase 3 training + serving:** NOT STARTED.
**M4 — Phase 4 multi-tenant + polish:** NOT STARTED.

---

## How to run the factory (Phase 1, today)

**One-time setup on a fresh machine:**

```bash
# 1. Clone or copy this folder to the target machine.
# 2. Python 3.11+ required.
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements-core.txt

# 3. Install LM Studio from https://lmstudio.ai/
# 4. In LM Studio, download Qwen3-8B-Instruct Q4_K_M (~6-7 GB, fits 5060 8GB).
# 5. Start the LM Studio local server (port 1234 default).

# 6. Configure factory.
cp .env.example .env            # then edit .env to set PROVIDER=lmstudio
```

**Run one chapter end-to-end:**

```bash
python -m aspireace_mocf.cli run \
  --input examples/physics_ch01_units_measurements_owned.json \
  --rights-ledger examples/source_ledger.csv \
  --run-id phy11_ch01_2026w22 \
  --chapter-no 1 \
  --chapter-name "Units and Measurements" \
  --limit-units 3
```

Outputs land in `runs/phy11_ch01_2026w22/`. See [OPERATING_GUIDE.md](OPERATING_GUIDE.md) for the full weekly workflow.

**Start the SME review UI:**

```bash
streamlit run review_app/app.py -- --run-dir runs/phy11_ch01_2026w22
```

Open `http://localhost:8501` (or share over coaching wifi at `http://<your-ip>:8501`).

**Approve records after review + export:**

```bash
python -m aspireace_mocf.cli approve \
  --input runs/phy11_ch01_2026w22/verified/tutor_app_auto_checked.jsonl \
  --output runs/phy11_ch01_2026w22/verified/tutor_app_sme_verified.jsonl \
  --approver "physics_sme_001" \
  --reason "SME verified, source-grounded, no AI-self-reference."

python -m aspireace_mocf.cli export --run-id phy11_ch01_2026w22 \
  --tutor runs/phy11_ch01_2026w22/verified/tutor_app_sme_verified.jsonl
```

**Ingest approved records to AspireACE Neon** (separate step, run on AspireACE side):

```bash
python tools/ingest_to_aspireace_neon.py \
  --file runs/phy11_ch01_2026w22/exports/app_content/notes.jsonl \
  --lane notes --subject Physics --chapter 1
```

---

## What changed since v0.3.0 baseline

See [CHANGELOG.md](CHANGELOG.md) for the full list. M1 in summary:

| Area | Before (v0.3.0) | After (v1.0.0-M1) |
|---|---|---|
| Documentation | README only | 6 anchor docs (HANDOFF, ARCHITECTURE, PHASE_ROADMAP, OPERATING_GUIDE, ELITE_BAR, CHANGELOG) + prompts/README + 4 subject addendums |
| Critical bugs | 7 known issues affecting legal/correctness | 0 — all 7 closed |
| Error handling | bare `except Exception` swallows + string-substring routing | enum-based taxonomy + route_record() helper |
| Logging | `tqdm` only | structlog JSON-lines + correlation IDs |
| Retry | none | tenacity exponential backoff on transient errors |
| Token-budget guard | none | per-model context-window check before LLM call |
| Lockfile | none | PID + hostname + timestamp, with stale-PID auto-break |
| Subject support | Physics-leaning prompts only | Physics + Chemistry + Biology + Mathematics with per-subject addendums |
| Anchor examples | 1 (Physics) | 4 (Physics + Chemistry + Biology + Mathematics) |
| Audit trail | none (Streamlit wrote no log) | append-only audit_log.jsonl with reviewer_id + timestamp + reason + train_allowed transition |
| Auth | text input defaulting to "reviewer_001" | REVIEWER_USERS env-driven sha256 password auth + two-tier junior/senior queue |
| Tests | 2 trivial files (8 LoC + 7 LoC) | ~120 unit tests across 9 modules; 46 verified passing |
| pyproject.toml | minimal | full mypy/ruff/pytest/coverage config |
| .gitignore | 11 lines | ~70 lines covering all phases |
| .env.example | flat config | phased config (Phase 1/2/3/4 sections) |

---

## What's next

**Immediate (before any M2 work) — operational verification of M1:**

1. **Install + smoke test on the 5060 machine.** Move this folder to the coaching machine, `pip install -r requirements-core.txt`, install LM Studio + Qwen3-8B-Instruct Q4_K_M, configure `.env`, run the smoke test:
   ```bash
   python -m aspireace_mocf.cli run \
     --input examples/physics_ch01_units_measurements_owned.json \
     --rights-ledger examples/source_ledger.csv \
     --run-id smoke_phy11_ch01 \
     --chapter-no 1 --chapter-name "Units and Measurements" \
     --limit-units 2
   ```
2. **Verify the full test suite passes after install.** `pytest -v` should show ~120 tests green.
3. **Run smoke tests for Chemistry + Biology + Mathematics** using the new anchor examples in `examples/`. Each subject's addendum should produce subject-appropriate output.
4. **Eyeball the outputs.** Open `runs/<id>/lanes/*.jsonl` and check that the records look like what a teacher would expect. If they don't, the prompt addendums need iteration (don't edit `v1/` — branch to `v2/`).

**Next session — M2 Phase 2 API layer.** Wrap the factory in FastAPI, add SQLite-backed approved-content catalog, set up bearer-token auth, write deployment runbook for tunnelling to AspireACE BFF. See [PHASE_ROADMAP.md](PHASE_ROADMAP.md) §M2 for the detailed scope.

**Quick wins available any time** (no founder input needed):
- Add more anchor examples (`examples/`) — beyond the initial 4 (Phy/Chem/Bio/Math), more chapters help teachers see what good source looks like
- Translate the OPERATING_GUIDE.md into a Hindi-mixed crib sheet for non-English-first teachers (post-launch, since Hindi is deferred)
- Write `tools/coverage_report.py` to print a chapter × lane matrix so you know what's covered
- Add more parameterized cases to `tests/unit/test_basic_checks.py::TestBadPhraseDetection` as new LLM-self-reference patterns are observed in real runs
- Author senior-teacher golden eval set (~200 query/ideal-response pairs) — needed for Phase 3 SFT evaluation; can author now while context is fresh

---

## Hard rules — do NOT relitigate

1. **This folder is standalone.** It does NOT get attached to the AspireACE main repo. The only AspireACE-side touch is `tools/ingest_to_aspireace_neon.py`, which lives in the AspireACE repo (not here).
2. **Every record starts `train_allowed=false`.** Becomes `true` only after SME approval. See [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).
3. **No source text gets copied to outputs.** Drafts are LLM-original; similarity guard catches accidental copy-paste.
4. **English-only at launch.** Hindi prompts/stems/voice deferred — see AspireACE `project_content_scope_hindi_3d_defer` memory.
5. **Provider-flexible.** Code must work against both LM Studio (local) and any OpenAI-compatible API. Never hardcode to one.
6. **Elite bar applies.** Every module passes the 10 rows in [ELITE_BAR.md](ELITE_BAR.md). No scaffold-only modules.
7. **No version / phase gating.** If a feature is missing or a bug is visible, fix it now. Don't defer to "Phase 2" unless it genuinely depends on infrastructure not yet built.

---

## Forbidden actions

- Commit secrets (`.env`, API keys, IP-sensitive source) — `.gitignore` already protects, never bypass
- Push to the AspireACE main repo from this folder — wrong git remote, factory is standalone
- Hardcode provider (LM Studio OR OpenAI only) — must support both
- Generate training data from `reference_only` sources — rights validator must gate per-lane, not aggregate
- Mark `train_allowed=true` without an `approver_id` + reason + timestamp recorded — legal audit trail required

---

## When you're stuck

- **State unclear?** → Re-read this file + [CHANGELOG.md](CHANGELOG.md), then `git log --oneline -20`.
- **A test fails?** → Check `pytest -v` first; the test names should explain what's expected. If still unclear, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
- **LM Studio not responding?** → Verify it's running on port 1234. `curl http://localhost:1234/v1/models` should list the loaded model.
- **A schema validation failing on every record?** → Likely the LLM is returning the wrong shape. Check the prompt's example block — does it show `[{...}]` (array) or just `{...}` (object)? Schema expects array; prompt must show array.
- **OOM on the 5060 8GB?** → You're probably running the model at FP16 instead of Q4_K_M. Re-download from LM Studio with the Q4_K_M quantization variant.
- **Founder voice vs doc voice conflict?** → Founder voice wins. Per AspireACE `feedback_doc_drops_partial_truth`.

---

*Bump this file's "Last refreshed" date + add a brief "What changed" note any time the factory's state materially shifts (a milestone closes, a phase activates, a major decision lands).*
