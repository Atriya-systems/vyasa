# ARCHITECTURE

**Purpose:** Full system architecture of the AspireACE ModelOps + ContentOps Factory, across all four phases. This is the technical map; for state / what's-shipped see [HANDOFF.md](HANDOFF.md), for the phase plan see [PHASE_ROADMAP.md](PHASE_ROADMAP.md).

---

## 1. The big picture

The factory is a **pipeline that turns owned/SME-licensed source material into nine kinds of structured output**, gated by rights + quality, then either dropped to disk for manual ingestion (Phase 1) or served via API (Phase 2+) or used to fine-tune a tutor LLM that itself becomes an API (Phase 3+).

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                  AspireACE ModelOps + ContentOps Factory      │
                    │                                                                │
   Source           │   ┌──────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐ │
   material   ────▶ │   │  Intake   │──▶│ Rights  │──▶│  Source  │──▶│ 9-lane  │ │
   (teacher's       │   │ (form /   │    │  ledger │    │  units   │    │ LLM gen │ │
    notes /         │   │  OCR /    │    │  gate   │    │  builder │    │ (Qwen3) │ │
    whiteboard      │   │  WhatsApp)│    │         │    │          │    │         │ │
    photo /         │   └──────────┘    └─────────┘    └──────────┘    └────┬────┘ │
    paste)          │                                                        │      │
                    │                                                        ▼      │
                    │   ┌──────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐ │
                    │   │  Export   │◀──│ Approve │◀──│  Review  │◀──│  Verify │ │
   Approved   ◀──── │   │ JSONL +  │    │  (SME   │    │   UI     │    │ (schema │ │
   JSONL +          │   │ manifest │    │  gate)  │    │(Streamlit│    │  + sim  │ │
   manifest         │   │          │    │         │    │  /API)   │    │ +judge) │ │
                    │   └──────────┘    └─────────┘    └──────────┘    └─────────┘ │
                    └────────┬─────────────────────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────┴───────────────┐
              │                              │
              ▼                              ▼
   tools/ingest_to_aspireace_neon.py    Phase 3 training pipeline
   (Phase 1 manual / Phase 2 auto)      (LoRA SFT on approved data)
              │                              │
              ▼                              ▼
   AspireACE Neon DB                  Trained tutor LLM
   (questions, notes, tricks,         (vLLM serving, OpenAI-compat API)
    rag_chunks tables)                       │
                                             ▼
              ┌──────────────────────────────┘
              │
              ▼
   AspireACE app + 3rd party clients
   (Phase 3-4: call /tutor/v1/chat/completions)
```

---

## 2. Module layout

```
src/aspireace_mocf/
├── __init__.py              package version, public surface
├── cli.py                   argparse entry: run, agent-run, approve, export, api-serve, validate-source
│
├── settings/                configuration
│   ├── base.py              core Settings dataclass (env-driven)
│   ├── subjects.py          per-subject config overrides (Phy/Chem/Bio/Maths)
│   └── phases.py            per-phase feature flag matrix
│
├── pipeline/                content generation pipeline
│   ├── source_units.py      LLM-call: source text → structured units
│   ├── lane_generation.py   LLM-call: units → per-lane records (9 lanes)
│   ├── verify.py            schema + similarity + LLM-judge gate; routes to queues
│   ├── approve.py           SME approval: sets sme_verified + train_allowed + audit
│   ├── export.py            train/eval JSONL split + app-content export
│   ├── rag_offline.py       RAG chunk emission + offline bundle
│   ├── manifest.py          run manifest (sha256, counts, rights summary)
│   ├── ids.py               deterministic ID generation
│   ├── paths.py             run directory layout
│   ├── runner.py            orchestrates the whole pipeline for one chapter
│   ├── checkpoint.py        resume-from-interruption
│   ├── lockfile.py          concurrent-run protection
│   └── orchestrator.py      multi-chapter batch runner
│
├── providers/               LLM provider abstraction
│   ├── llm.py               unified client (LMStudio or OpenAI-compat)
│   ├── lmstudio.py          LM Studio specialization
│   ├── openai_compat.py     OpenAI / OpenAI-compatible specialization
│   ├── retry.py             tenacity-based exponential backoff
│   └── token_budget.py      context window management
│
├── validators/              quality gates
│   ├── basic_checks.py      record shape + bad-phrase + train-allow rules
│   ├── rights_validator.py  per-lane CSV ledger gating
│   ├── schema_validator.py  JSON Schema validation wrapper
│   ├── similarity.py        TF-IDF cosine guard vs source
│   ├── latex_validator.py   equation validity check
│   └── conflict_detector.py cross-teacher source-overlap detection
│
├── utils/                   cross-cutting helpers
│   ├── hashing.py           SHA-256 for provenance
│   ├── jsonio.py            JSON / JSONL read+write
│   ├── text.py              normalization (formula cleanup, whitespace, dehyphenation)
│   ├── logging.py           structured logging (JSON lines, levels, correlation IDs)
│   └── errors.py            enum-based error taxonomy (no string-matching)
│
├── agents/                  LangGraph orchestration
│   ├── supervisor.py        pipeline → supervisor → {retry, human, finish}
│   └── orchestrator.py      multi-chapter agent
│
├── tracking/                run telemetry
│   ├── mlflow_logger.py     MLflow params + metrics + artifacts
│   ├── run_stats.py         per-run metrics, costs, latencies
│   └── catalog.py           searchable index of approved records
│
├── storage/                 [Phase 2+] approved-content catalog
│   ├── sqlite_store.py      default catalog (single-tenant)
│   ├── postgres_store.py    [Phase 4] multi-tenant catalog
│   └── migrations/          catalog schema versioning
│
├── api/                     [Phase 2+] HTTP service layer
│   ├── server.py            FastAPI app
│   ├── auth.py              bearer token + [Phase 4] multi-tenant key mgmt
│   ├── routes/
│   │   ├── generate.py      POST /generate/{lane}
│   │   ├── content.py       GET  /content/{lane}
│   │   ├── pipeline.py      POST /pipeline/run + GET status
│   │   ├── review.py        POST /review/approve
│   │   ├── tutor.py         [Phase 3] POST /tutor/v1/chat/completions (OpenAI-compat)
│   │   └── admin.py         [Phase 4] tenant mgmt, usage, quotas
│   └── middleware/
│       ├── rate_limit.py    [Phase 4]
│       └── usage_tracking.py [Phase 4]
│
└── training/                [Phase 3] training pipeline
    ├── data_prep.py         approved JSONL → SFT training format
    ├── eval_harness.py      trained model vs senior-teacher golden set
    ├── golden_set.py        manage the eval set
    └── model_registry.py    version + tag trained models
```

---

## 3. Data flow — one chapter, end to end

**Phase 1 (batch only):**

```
1. Teacher submits source via intake (web form / OCR / paste)
   → lands at runs/<run_id>/input/source.json + entry in source_ledger.csv

2. CLI: aspireace-mocf run --input ...
   → LM Studio called via providers/llm.py
   → pipeline/source_units.py decomposes source into N source units
   → pipeline/lane_generation.py generates records for each of 9 lanes
   → pipeline/verify.py runs schema + similarity + (optional) LLM-judge gate
   → records route to verified/<lane>_auto_checked.jsonl
              or       queues/<lane>_fix_queue.jsonl
              or       queues/<lane>_human_review_queue.jsonl
              or       verified/<lane>_rejected.jsonl
   → pipeline/rag_offline.py emits RAG chunks + offline bundle
   → pipeline/manifest.py writes run manifest with SHA-256 + counts

3. SME opens Streamlit (review_app/app.py)
   → reviews each queue file
   → clicks Approve / Reject per record
   → on Approve: pipeline/approve.py writes <lane>_sme_verified.jsonl
                 with train_allowed=true, approver_id, reason, timestamp

4. CLI: aspireace-mocf export --run-id ...
   → splits SME-verified records into train/eval per eval_ratio
   → writes exports/training/<lane>_train.jsonl + _eval.jsonl
   → copies app_binding/*.json into exports/manifests/

5. (AspireACE side) tools/ingest_to_aspireace_neon.py
   → reads approved JSONL
   → maps to live Neon table shape (questions, notes, tricks, rag_chunks)
   → INSERT batch with source_unit_id traceability
   → Records show up in the app on next student session
```

**Phase 2+ adds:**

```
- Instead of manual ingest, the AspireACE BFF calls:
    GET /content/notes?chapter=X
  which serves from the factory's SQLite catalog (auto-fresh from approved JSONL).
- For uncached requests, BFF can call:
    POST /generate/notes  { chapter, depth }
  which runs the LLM live and caches the response back.
```

**Phase 3+ adds:**

```
- The trained tutor LLM is served via:
    POST /tutor/v1/chat/completions
  (OpenAI-compatible — clients use existing OpenAI SDKs by changing base URL).
- AspireACE BFF's jarvis_control_layer.py can swap from Anthropic to /tutor by config.
- 3rd parties subscribe to the same endpoint.
```

**Phase 4+ adds:**

```
- Per-tenant API keys + usage tracking + rate limits
- Versioned API contracts (v1, v2) so clients pin
- Multi-region serving if latency matters for global customers
```

---

## 4. Storage layout per run

```
runs/<run_id>/
├── input/
│   └── source.json                       original source material (gitignored)
├── source_units/
│   ├── source_units.jsonl                LLM-decomposed units
│   └── rejected_source_units.jsonl       units that failed schema
├── lanes/                                draft outputs per lane
│   ├── base_subject.jsonl
│   ├── tutor_app.jsonl
│   ├── content_generator.jsonl
│   ├── notes.jsonl
│   ├── tricks.jsonl
│   ├── misconceptions.jsonl
│   ├── dpp_tests.jsonl
│   ├── grading_feedback.jsonl
│   └── revision.jsonl
├── verified/                             post-verification routing
│   ├── <lane>_auto_checked.jsonl         passed all gates, awaiting SME
│   ├── <lane>_sme_verified.jsonl         approved (train_allowed=true)
│   ├── <lane>_rejected.jsonl             permanently rejected
│   └── manual_sme_verified.jsonl         Streamlit manual approvals
├── queues/                               human-review queues
│   ├── <lane>_fix_queue.jsonl            similarity / fix-required
│   └── <lane>_human_review_queue.jsonl   uncertain / judge-error
├── rag/
│   └── chunks.jsonl                      RAG-ready chunks
├── offline/
│   └── chapter_bundle.json               offline app bundle
├── exports/                              final outputs for downstream consumers
│   ├── training/<lane>_{train,eval}.jsonl    fine-tuning inputs
│   ├── app_content/<lane>.jsonl              app-ingest inputs
│   ├── rag/chunks.jsonl                      RAG-ingest inputs
│   ├── offline/chapter_bundle.json           offline bundle copy
│   └── manifests/{aspireace_surface,engine_binding,feature_flag,runtime_routes}.json
├── reports/
│   ├── run_report.json                   counts + rights summary
│   └── <lane>_verification_report.json   per-lane verification stats
└── manifests/
    └── run_manifest.json                 SHA-256 of input + outputs + status
```

`runs/` is gitignored. Source material + outputs stay local-disk + Neon.

---

## 5. The 9 lanes — what they each produce

| Lane | Lane type | Output shape | AspireACE consumer | Training-allowable? |
|---|---|---|---|---|
| `base_subject` | training | `{ text, metadata }` | Future tutor LLM base knowledge | Yes (after SME approval) |
| `tutor_app` | training | `{ messages, metadata }` | Future tutor LLM doubt-solve voice | Yes (after SME approval) |
| `content_generator` | training | `{ messages, metadata }` | Future content-author LLM | Yes (after SME approval) |
| `notes` | app content | `{ card_id, title, body, metadata }` | CL-260 Notes Library | No (app-only) |
| `tricks` | app content | `{ card_id, title, body, metadata }` | CL-155 Short Trick Generator | No (app-only) |
| `misconceptions` | app content | `{ card_id, title, body, metadata }` | ENG-013 + SPRE intervention | No (app-only) |
| `dpp_tests` | app content | `{ card_id, question_text, options, answer, metadata }` | CL-080 DPP + mock tests | No (app-only) |
| `grading_feedback` | app content | `{ card_id, rubric, exemplars, metadata }` | ENG-003 HSGE Cognitive Rubric Runtime | No (app-only) |
| `revision` | app content | `{ card_id, title, body, recall_probe, metadata }` | EDU-032 Revision Planner + ENG-054 | No (app-only) |

Plus auxiliary outputs:
- `rag_chunks` — text+metadata for ENG-002 RAG retrieval (Qdrant / pgvector)
- `offline_bundle` — chapter packed for low-connectivity offline mode

---

## 6. The rights gate — why every record starts `train_allowed=false`

Every LLM-drafted record carries `metadata.train_allowed = false` until an SME explicitly approves it via the Streamlit review UI or CLI `approve` command. This is enforced at three checkpoints:

1. **At generation:** `lane_generation.py:_normalize_*_record` sets `train_allowed=false`, `quality_status="draft"`, `drafted_by="api_model"`.
2. **At verification:** `validators/basic_checks.py:record_errors` rejects any record where `drafted_by="api_model"` AND `train_allowed=true` AND `quality_status != "sme_verified"`.
3. **At approval:** `pipeline/approve.py` is the **only** code path that sets `train_allowed=true`, and it requires `approver_id` + `reason` + `approved_at_utc` + writes to an append-only audit log.

This is the legal moat. Removing or weakening this gate is a hard violation. See [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).

---

## 7. The provider abstraction — why LM Studio + OpenAI both work

`providers/llm.py` exposes a single `LLMClient` class. Internally it routes to:
- `providers/lmstudio.py` for `PROVIDER=lmstudio` (local Qwen3-8B via LM Studio's OpenAI-compatible server)
- `providers/openai_compat.py` for `PROVIDER=openai` (real OpenAI, Together AI, Fireworks, Groq, any OpenAI-compatible endpoint)

Same call signature. Same JSON-schema response coercion. Same retry policy via `providers/retry.py`. Same token-budget guard via `providers/token_budget.py`.

**This is why "free during Phase 1, scale to cloud in Phase 2-3" works without code changes** — only `.env` changes.

---

## 8. The supervisor — what LangGraph adds vs CLI-only

CLI mode (`aspireace-mocf run`) runs the whole pipeline sequentially. Fails fast if any step errors.

Agent mode (`aspireace-mocf agent-run`) wraps the same pipeline in a LangGraph state machine: `pipeline → supervisor → {retry, human, finish}`. The supervisor inspects per-lane counts, decides:
- If 1+ lane returned zero accepted records → `retry` (up to `AGENT_MAX_RETRIES`)
- If any queue has fix-required or human-review items → `human` (interrupts with `langgraph.types.interrupt` for SME review)
- Else → `finish`

With `--human-in-loop`, the supervisor pauses at `human` until you resume the graph. Useful for unattended overnight runs where you want to wake up to a queue ready for review, not a half-finished run.

Checkpointer is SqliteSaver (per-run, persisted to `runs/<run_id>/agent_state.sqlite`). If the process dies mid-run, resume picks up where it left off.

---

## 9. Phase deltas — what changes across phases

| Phase | What's new | What's enabled | What's disabled |
|---|---|---|---|
| **Phase 1** | Everything in the pipeline (gen, verify, approve, export) | Batch CLI runs, Streamlit review, manual Neon ingest | No HTTP API, no trained model, no multi-tenant |
| **Phase 2** | `src/.../api/`, `storage/sqlite_store.py`, FastAPI server | Internal HTTP API for AspireACE BFF, SQLite catalog of approved content | No trained tutor, no public access, no rate limit |
| **Phase 3** | `src/.../training/`, `serving/`, `api/routes/tutor.py` | LoRA SFT runs, vLLM serving, `/tutor/v1/chat/completions` (OpenAI-compat) | No multi-tenant billing |
| **Phase 4** | `storage/postgres_store.py`, `api/middleware/rate_limit.py`, `api/middleware/usage_tracking.py`, `api/routes/admin.py` | Per-tenant API keys, rate limiting, usage tracking, billing hooks, versioned contracts | (everything enabled) |

Each phase is **purely additive**. No earlier-phase code is removed. Activating later phases is a config flag flip, not a code rewrite.

---

## 10. Key non-obvious decisions

- **`runs/` is per-chapter, not per-day.** A "run" = one chapter through the 9 lanes. Multi-chapter weekly runs use `orchestrator.py` which spawns one sub-run per chapter and aggregates.
- **`source_id` is the rights-gate key.** Every record traces back to a source_id; if the rights ledger blocks that source_id for a lane, the lane skips that source entirely. No partial trust.
- **JSON schema validation happens twice.** Once at generation (catch malformed LLM output) and once at verify (catch drift if records are hand-edited). Belt + suspenders.
- **Similarity guard runs against source text only, not against earlier-generated records.** Goal: catch copy-paste from source, not enforce diversity across drafts. Diversity is a separate concern (judge prompt).
- **MLflow + DVC are optional, off by default.** Wired in case you want them for Phase 3 SFT experiments, but Phase 1 batch runs don't need them.
- **Streamlit is the SME UI for Phase 1, NOT the long-term answer.** Phase 4 expectation: migrate review into a real Next.js admin panel inside AspireACE. Streamlit is "good enough to ship, not the final shape."

---

## 11. What this architecture explicitly does NOT do

These are non-goals that future agents/operators should not "fix" by accident:

- **No automatic prod-DB writes.** Even in Phase 2 API mode, writes to AspireACE Neon are explicit (via `ingest_to_aspireace_neon.py` or a deliberate API call). Factory never writes to AspireACE DB on its own.
- **No live student-facing inference path.** Phase 1-2 generate batch content. Phase 3+ adds inference, but it's the AspireACE BFF's choice when to call it. Factory doesn't push.
- **No translation or multi-language.** English only at launch (per AspireACE `project_content_scope_hindi_3d_defer`). Hindi/regional come post-launch via prompt-set additions.
- **No image generation.** Factory is text-only. Diagrams come from teachers' scanned material or a separate (future) image pipeline.
- **No autonomous teacher impersonation.** The trained tutor LLM (Phase 3) is *grounded* in teachers' approved material but doesn't claim to be a specific teacher. The voice is "AspireACE pedagogy," not "Mr. Sharma."

---

*Update this file when the architecture genuinely changes (new module, removed module, phase boundary shifts). Not for every code edit.*
