# HANDOFF — Read this first

**This is the entry point for any agent or operator picking up the factory. Read this in full before touching anything else.**

**Project:** AspireACE ModelOps + ContentOps Factory
**Owner:** Piyush Batra · ATRIYA SYSTEMS PVT LTD · CONFIDENTIAL
**Version:** v1.0.0 (in progress) — see CHANGELOG.md
**Last refreshed:** 2026-05-25 (M1 build session start)

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

**v1.0.0 in progress.** Elite enhancement pass underway. See [CHANGELOG.md](CHANGELOG.md) for what's landed and what's open. See [PHASE_ROADMAP.md](PHASE_ROADMAP.md) for the milestone plan.

**M1 — Foundation + Phase 1 hardening:** IN PROGRESS
- Foundational docs (this file + 5 siblings) — being written
- 7 critical bug fixes — pending
- Core infrastructure (logging, errors, retry, lockfile, token budget) — pending
- Multi-subject (Chem/Bio/Maths prompt sets + anchors) — pending
- Real tests + hardened config — pending

**M2 — Phase 2 API layer:** NOT STARTED (depends on M1)
**M3 — Phase 3 training + serving:** NOT STARTED (depends on M2)
**M4 — Phase 4 multi-tenant + polish:** NOT STARTED (depends on M3)

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

See [CHANGELOG.md](CHANGELOG.md). Short version:

- M1 hardening pass: 7 critical bugs fixed, multi-subject support added, core infra (logging/errors/retry/lockfile) introduced, real test coverage added, foundation docs authored.

---

## What's next

**This session:** finish M1 (see [CHANGELOG.md](CHANGELOG.md) in-progress notes for the precise stopping point).

**Next session:** M2 — Phase 2 API layer. Wrap the factory in FastAPI, add SQLite-backed approved-content catalog, set up bearer-token auth, write deployment runbook for tunnelling to AspireACE BFF. See [PHASE_ROADMAP.md](PHASE_ROADMAP.md) §M2 for the detailed scope.

**Quick wins available any time** (no founder input needed):
- Add more anchor examples (`examples/`) — anything beyond the initial 6-8 helps teachers see what good source looks like
- Translate the OPERATING_GUIDE.md into a Hindi-mixed crib sheet for non-English-first teachers (post-launch, since Hindi is deferred)
- Write `tools/coverage_report.py` to print a chapter × lane matrix so you know what's covered

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
