# OPERATING GUIDE

**Purpose:** Day-to-day operation of the factory. Setup, weekly workflow, teacher onboarding, troubleshooting. Practical, not architectural.

For architecture see [ARCHITECTURE.md](ARCHITECTURE.md). For state see [HANDOFF.md](HANDOFF.md). For phase plan see [PHASE_ROADMAP.md](PHASE_ROADMAP.md).

---

## 1. First-time setup on a fresh machine

Target: a Linux box, Mac, or Windows machine with at least:
- 16 GB RAM
- 8 GB VRAM if running Qwen3-8B locally (5060 / 3070 / 4060 / better)
- 50 GB free disk (model + runs + LM Studio overhead)
- Python 3.11+
- Internet (one-time, for downloading model + deps)

### Step 1.1 — clone or copy this folder

```bash
# Either git clone (when factory has a remote):
git clone <factory-repo-url> aspireace_factory
cd aspireace_factory

# Or scp from your machine to the 5060 box:
scp -r aspireace_modelops_contentops_factory_v3/ coaching-machine:/srv/factory/
ssh coaching-machine
cd /srv/factory
```

### Step 1.2 — Python environment

```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate

# Mac/Linux:
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements-core.txt
```

If you'll do Phase 3 training on this same machine:
```bash
pip install -r requirements-training.txt   # adds torch, transformers, peft, trl, accelerate, mlflow
```

If you'll run the Streamlit review UI on this machine:
```bash
pip install -r requirements-review.txt     # adds streamlit, pandas
```

### Step 1.3 — LM Studio + Qwen3-8B

1. Download LM Studio from https://lmstudio.ai/
2. Open LM Studio → Discover tab → search "Qwen3-8B-Instruct"
3. Download the **Q4_K_M** quantization (~6-7 GB). Critical — do NOT download FP16 (won't fit 5060 8 GB).
4. Once downloaded, click the loaded-model dropdown at the top → select Qwen3-8B-Instruct.
5. Open the **Local Server** tab → click **Start Server**. Should bind to `http://localhost:1234`.
6. Verify from a shell:
```bash
curl http://localhost:1234/v1/models
```
Should return a JSON list including your loaded model.

### Step 1.4 — configure factory

```bash
cp .env.example .env
```

Edit `.env`:

```env
PROVIDER=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_API_KEY=lm-studio
MODEL_NAME=qwen3-8b-instruct

CLASS_LEVEL=11
SUBJECT=Physics
EXAM_TARGETS=JEE,NEET
SOURCE_TYPE=SME_OWNED

BASE_RECORDS_PER_UNIT=4
TUTOR_RECORDS_PER_UNIT=5
CONTENTGEN_RECORDS_PER_UNIT=5
APP_CARDS_PER_UNIT=2
DPP_RECORDS_PER_UNIT=3
RUBRIC_RECORDS_PER_UNIT=2
REVISION_RECORDS_PER_UNIT=3

EVAL_RATIO=0.10
RANDOM_SEED=42
ENABLE_LLM_JUDGE=false
SIMILARITY_WARN_THRESHOLD=0.82

AGENT_MAX_RETRIES=2
HUMAN_IN_LOOP=false
```

### Step 1.5 — smoke test

```bash
python -m aspireace_mocf.cli run \
  --input examples/physics_ch01_units_measurements_owned.json \
  --rights-ledger examples/source_ledger.csv \
  --run-id smoke_test_$(date +%Y%m%d_%H%M) \
  --chapter-no 1 \
  --chapter-name "Units and Measurements" \
  --limit-units 2
```

Expect:
- Progress bars for each lane
- Final JSON printed with `outputs` dict
- `runs/smoke_test_<ts>/` populated with directories
- `runs/smoke_test_<ts>/manifest/run_manifest.json` containing counts and rights summary

If anything fails, see §7 Troubleshooting.

### Step 1.6 — run tests

```bash
pytest tests/ -v
```

All green confirms install + config is sound.

---

## 2. Adding a new teacher (intake onboarding)

When a new teacher joins the content team:

### Step 2.1 — IP contract

Verify their employment contract assigns IP of materials authored during employment to ATRIYA. If not, fix that first — talk to your legal counsel. This is the legal foundation of `train_allowed=true`.

### Step 2.2 — Add to source ledger

Edit `examples/source_ledger.csv` (or your production `content/rights/source_ledger.csv` if you've moved it):

```csv
source_id,source_type,owner,commercial_use_allowed,ai_training_allowed,derivative_allowed,reference_only,license_doc,approved_for,teacher_id,seniority
SME_PHY11_ASHWIN_001,SME_OWNED,Atriya Systems,true,true,true,false,IP_CONTRACT_ASHWIN.pdf,"base_subject;tutor_app;content_generator;app_content;rag;offline",teacher_ashwin,senior
```

Convention for `source_id`: `SME_<SUBJECT><CLASS>_<TEACHER>_<SERIAL>` so every submission is traceable to a teacher.

### Step 2.3 — give them intake access

If using the web form (`intake/web_form/server.py`):
- Create their account in the form's user table
- Send them the URL + login

If using paste-into-folder (Phase 1 simplest):
- Show them where to drop `.json` files
- Walk through one example

If using OCR (`intake/ocr_bridge.py`):
- Show them how to take a clear photo of whiteboard / handwritten notes
- Walk through how to verify the OCR output before submission

### Step 2.4 — first run together

Have them submit one chapter's source. Run the factory together. Walk through Streamlit review. Approve 5-10 records together so they see the loop. Show them the resulting cards in the app.

The goal: make the loop **visible** to them. Teachers stay engaged when they see their work landing in students' hands.

---

## 3. Weekly workflow — the canonical rhythm

```
Mon-Fri: Teachers submit source as they finish teaching topics
         → lands in content_source_queue / intake folder
         → tagged with subject, chapter, teacher_id

Fri evening: You run the factory batch
             → python tools/batch_runner.py --week 2026-W22
             → factory processes all submitted source overnight
             → outputs land in runs/<week>/<chapter>/

Sat morning: Teachers come to coaching for content session (or remote)
             → Open Streamlit at http://factory:8501
             → Each teacher reviews their subject's queue
             → ~1 hour, ~50 records each, mostly approve

Sat afternoon: You run the ingest script
               → python tools/ingest_to_aspireace_neon.py
                       --week 2026-W22 --lanes notes,tricks,dpp_tests,rag
               → Approved records land in AspireACE Neon
               → Smoke-test: open AspireACE app, verify new content visible

Sun: Students hit fresh content in the app. No one knows the pipeline ran.

Mon: Generate weekly digest
     → python tools/teacher_digest.py --week 2026-W22
     → Each teacher gets "your chunk X → produced Y cards → Z students saw → W found helpful"
     → Reinforces the loop
```

---

## 4. Common operations

### 4.1 — Run one chapter end-to-end (manual)

```bash
python -m aspireace_mocf.cli run \
  --input <path-to-source.json> \
  --rights-ledger <path-to-ledger.csv> \
  --run-id <unique-id> \
  --chapter-no <N> \
  --chapter-name "<Chapter Name>" \
  --llm-judge   # optional, enables LLM-as-judge quality gate
```

### 4.2 — Run agent mode (with retries + human gate)

```bash
python -m aspireace_mocf.cli agent-run \
  --input <path> --rights-ledger <path> \
  --run-id <id> --chapter-no <N> --chapter-name "..." \
  --llm-judge --human-in-loop
```

### 4.3 — Approve records after SME review

```bash
python -m aspireace_mocf.cli approve \
  --input runs/<run_id>/verified/<lane>_auto_checked.jsonl \
  --output runs/<run_id>/verified/<lane>_sme_verified.jsonl \
  --approver "teacher_ashwin" \
  --reason "Reviewed by Ashwin (senior), source-grounded, no AI self-reference."
```

### 4.4 — Export training + app content

```bash
python -m aspireace_mocf.cli export --run-id <id> \
  --base runs/<id>/verified/base_subject_sme_verified.jsonl \
  --tutor runs/<id>/verified/tutor_app_sme_verified.jsonl \
  --contentgen runs/<id>/verified/content_generator_sme_verified.jsonl
```

### 4.5 — Start the Streamlit review UI

```bash
streamlit run review_app/app.py -- --run-dir runs/<run_id>
```

Or, scoped to a specific lane:

```bash
streamlit run review_app/app.py -- --run-dir runs/<run_id> --lane tutor_app
```

### 4.6 — Resume a crashed run

If the factory died mid-run (power cut, OOM, kill):

```bash
python -m aspireace_mocf.cli resume --run-id <crashed-run-id>
```

Reads the checkpoint, picks up at the last completed lane.

### 4.7 — Ingest approved records to AspireACE Neon

Run from the AspireACE main repo (this script lives there, not here):

```bash
cd /path/to/aspireace-app
python tools/ingest_to_aspireace_neon.py \
  --factory-run-dir /srv/factory/runs/<run_id> \
  --lanes notes,tricks,dpp_tests,rag_chunks \
  --neon-url $NEON_DATABASE_URL
```

### 4.8 — Coverage report (what's covered, what's not)

```bash
python tools/coverage_report.py --output reports/coverage_$(date +%F).json
```

Prints a chapter × lane matrix: which chapters have been processed, how many records per lane.

### 4.9 — Weekly teacher digest

```bash
python tools/teacher_digest.py --week 2026-W22 --output reports/digest_2026-W22.json
```

Reads `runs/`, `runs/<id>/verified/*_sme_verified.jsonl`, and (if available) AspireACE Neon usage telemetry, and emits a per-teacher summary.

---

## 5. Configuration knobs that matter

Most are in `.env`. The ones you'll actually tune:

| Variable | Default | When to change |
|---|---|---|
| `PROVIDER` | `lmstudio` | Switch to `openai` when you want cloud LLM (more capable but costs $) |
| `MODEL_NAME` | `qwen3-8b-instruct` | Try `qwen2.5-7b-instruct` if Qwen3 isn't released yet, or any local OpenAI-compat model |
| `BASE_RECORDS_PER_UNIT` | 4 | Reduce to 2 if you want faster iteration; raise to 6+ for SFT dataset bulk |
| `TUTOR_RECORDS_PER_UNIT` | 5 | Same logic |
| `EVAL_RATIO` | 0.10 | 10% of approved records reserved for eval; raise to 0.20 if you have a lot of data |
| `RANDOM_SEED` | 42 | Change to compare runs reproducibly |
| `ENABLE_LLM_JUDGE` | false | Set to true for stricter quality gate (uses LLM tokens; slows runs) |
| `SIMILARITY_WARN_THRESHOLD` | 0.82 | Lower to 0.75 for stricter source-copy detection; raise to 0.90 if too many false positives |
| `AGENT_MAX_RETRIES` | 2 | Raise to 5 if LM Studio drops connections often (transient issues) |
| `HUMAN_IN_LOOP` | false | Set to true for overnight unattended runs; supervisor pauses if review queue grows |

---

## 6. Capacity math

Useful for planning teacher workload and machine utilization.

**Per chapter, one source unit:**
- 9 lanes × per-lane record count (varies 2-5) = ~25-30 LLM calls
- Each call ~30-60 seconds on Qwen3-8B Q4_K_M on 5060
- Plus verification (LLM-judge optional): ~5-10 more calls
- **Total per source unit: ~15-25 minutes**

**Per chapter, ~5 source units (typical):**
- ~75-125 minutes (~1.5-2 hours)
- Output: ~30-50 records across all lanes

**Per week, 10 teachers × 5 chunks each = 50 chunks:**
- ~50 × 100 mins = ~80 hours of LM Studio time
- Run overnight Friday → Saturday morning (~12 hours runtime if parallelized, or batch in chunks)
- Output: ~1,500 records ready for SME review

**SME review at ~50 records/hour:**
- 1,500 ÷ 50 = ~30 person-hours of review
- Split across 10 teachers = 3 hours per teacher per week
- Or split across 4 senior teachers reviewing all subjects = ~7.5 hours each

That's the realistic baseline. Tune the per-unit record counts in `.env` if you need to dial pace up or down.

---

## 7. Troubleshooting

### 7.1 — LM Studio: "Connection refused" or "Cannot connect"

- Verify LM Studio is running. Open the app, check the Local Server tab.
- Verify the URL in `.env` matches LM Studio's server URL. Default is `http://localhost:1234/v1`.
- Curl the endpoint: `curl http://localhost:1234/v1/models`. If it fails, LM Studio isn't serving.
- Restart LM Studio's server (sometimes needs a fresh start after a model swap).

### 7.2 — LLM returns invalid JSON

- Check that your prompt's example block shows a JSON array `[{...}]`, not a single object `{...}`. The schema expects array.
- Some smaller models can't produce strict JSON. Try with `temperature=0.0` (set in `.env` via `TEMPERATURE=0.0`).
- Worst case: drop `response_format` (set `ENABLE_STRICT_JSON_SCHEMA=false` if/when that flag exists) and rely on `strip_json_fences` in `providers/llm.py`.

### 7.3 — OOM (out of memory) on the GPU

- You're probably running the model at FP16 instead of Q4_K_M.
- In LM Studio, unload the current model, search for the Q4_K_M variant, load that one instead.
- If still OOM, your GPU is too small. Options: rent A10G on Runpod for batch runs, or use a smaller model (Qwen2.5-3B Q4_K_M ~2 GB).

### 7.4 — Records all failing similarity check

- `SIMILARITY_WARN_THRESHOLD=0.82` is the default. If the LLM is being too literal with source text, similarity will trip on most records.
- Either lower the threshold (`0.85` for stricter) or raise it (`0.75` for more permissive) — wait, that's backwards. **Lower threshold = more strict** (catches more copy-paste). **Raise = more permissive** (allows closer paraphrases).
- For physics/chem where formulas must be copied verbatim, the LaTeX validator (added M1) should bypass formula similarity.

### 7.5 — Streamlit review UI shows no records

- Check that the run actually completed: `ls runs/<run_id>/queues/` — should contain `<lane>_fix_queue.jsonl` and `<lane>_human_review_queue.jsonl` files.
- If all queue files are empty (0 bytes), the records all passed gates → check `verified/<lane>_auto_checked.jsonl` instead; those don't need review unless you want a sanity check.

### 7.6 — Approval doesn't show up in `_sme_verified.jsonl`

- Verify you ran `aspireace-mocf approve` after Streamlit review (Streamlit writes to `verified/manual_sme_verified.jsonl`; the CLI `approve` command merges and properly tags).
- Check `verified/manual_sme_verified.jsonl` directly — if records are there, you skipped the CLI step.

### 7.7 — `pytest` failures after a code change

- Run `pytest -v --lf` (last failed) to see which test broke.
- Check `tests/integration/` — those exercise the full pipeline; failures there often surface real bugs.
- If a schema test fails, you likely changed a schema file without updating its consumers.

### 7.8 — Ingest to AspireACE Neon fails

- Verify `NEON_DATABASE_URL` is set in AspireACE side env.
- Check the target table has the columns the ingest script writes. Schema drift between factory and AspireACE = drop the new column at ingest time, log a warning, don't fail the whole batch.

---

## 8. What NOT to do

- Don't `git push` from this folder to AspireACE's git remote. Factory is standalone; if it has a remote, it's its own.
- Don't edit `runs/` files by hand. They're outputs; if you need to change something, fix the source + re-run.
- Don't disable the rights gate (`validators/rights_validator.py`) "temporarily." This is the legal foundation. If a source isn't approved for a lane, you cannot generate that lane from it — even for testing.
- Don't `pip install` packages directly without adding to `requirements-*.txt`. Reproducibility breaks fast otherwise.
- Don't share the `.env` file or the rights ledger CSV outside the team. Both contain IP-sensitive info.
- Don't run two factory instances against the same `run_id`. Lockfile (added M1) prevents this, but bypassing the lockfile causes data corruption.

---

## 9. Periodic maintenance

**Weekly:** review `runs/` disk usage; archive runs older than 8 weeks to cold storage if disk filling.

**Monthly:** check `requirements-core.txt` for security updates (`pip-audit` if installed).

**Quarterly:** review the rights ledger — any teachers left? IP contracts updated? Source types added (e.g., a new licensed corpus)?

**Annually:** sweep the prompts. NEET/JEE patterns shift; prompts may need updating to reflect current exam style. Version bump (`prompts/v2/`) when you do.

---

*Update this guide when operational workflows change (new tools, new intake channels, etc.). Not for every code edit.*
