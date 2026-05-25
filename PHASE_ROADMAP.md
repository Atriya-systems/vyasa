# PHASE ROADMAP

**Purpose:** The four-phase evolution of the factory, with concrete scope per phase, transition triggers, and what each milestone (M1..M4) delivers.

For the high-level "what is this" see [HANDOFF.md](HANDOFF.md). For module-level architecture see [ARCHITECTURE.md](ARCHITECTURE.md). For day-to-day operation see [OPERATING_GUIDE.md](OPERATING_GUIDE.md).

---

## The four phases at a glance

```
Phase 1 ───────▶ Phase 2 ───────▶ Phase 3 ───────▶ Phase 4
Batch CLI       Internal API     Trained Tutor     Multi-tenant
+ SME review    + Catalog DB     + OpenAI-compat   + Productized
+ Manual        + Single tenant  + LoRA SFT        + Rate limited
  ingest                         + vLLM serving    + Versioned API
```

**Each phase is purely additive.** Phase 2 adds an API layer ON TOP of Phase 1's batch pipeline; Phase 1 batch mode still works. Phase 3 adds a trained model ON TOP of Phase 2's API; the API still serves prompt-chain LLM if the trained model isn't ready. Etc.

**You don't have to commit to all four phases upfront.** Phase 1 alone delivers value (content for the app's cold start). Phases 2-4 unlock more leverage but aren't blockers for Phase 1 utility.

---

## Phase 1 — Batch content production

**Status (2026-05-25):** IN BUILD via M1.

**Goal:** Produce SME-approved app content (notes, tricks, DPP questions, revision cards, RAG chunks) for AspireACE's cold start. Run weekly on a small batch of teacher source. Manually ingest approved records into Neon.

**Operating model:**
- ~10 teachers submit source weekly via intake web form (or paste / OCR)
- Factory batches Friday evening → outputs JSONL files
- SMEs review Saturday morning via Streamlit (coaching wifi or VPS-hosted)
- Approved records exported, manually ingested to AspireACE Neon
- Students see new content Sunday onwards

**Why this is enough for now:** AspireACE is pre-beta. 50 internal students. The cost of operational complexity (auto-ingest, APIs, etc.) outweighs the benefit of automation until the pipeline is proven to produce reliable content. Phase 1 = prove the content is good enough.

**M1 deliverables** (in build):
- 7 critical bug fixes (silent exception swallow, rights gate logic, truncate-mid-validate, supervisor retry, prompt array shape, review_app audit trail, langgraph version pin)
- Multi-subject support (Chem / Bio / Maths prompt sets + 6-8 anchor sources)
- Core infrastructure: structured logging, error enums, tenacity retry + backoff, lockfile, token-budget guard, expanded bad-phrase list, precomputed similarity vectors
- Real test coverage (per-module unit tests + 4 subject-specific integration tests)
- Hardened config (pyproject, requirements, .gitignore, .env.example for all phases)
- Foundation docs (HANDOFF, ARCHITECTURE, PHASE_ROADMAP, OPERATING_GUIDE, ELITE_BAR, CHANGELOG, docs/* subset)
- Intake module (web form + OCR bridge + free-form normalizer)
- `tools/ingest_to_aspireace_neon.py` bridge script

**M1 transition criteria (Phase 1 declared operational):**
- ✅ Smoke test: one Physics chapter end-to-end (source → 9 lanes → SME approve → export → manual ingest → row in AspireACE Neon) passes
- ✅ Same smoke test for Chemistry, Biology, Mathematics
- ✅ All 7 critical bugs closed
- ✅ Test suite green (`pytest -v` zero failures)
- ✅ Two teachers have actually submitted source through intake and approved their own derivatives via Streamlit (operational, not just technical)
- ✅ At least one chapter's content visible in the AspireACE app to a real student

---

## Phase 2 — Internal API service

**Status:** NOT STARTED. Depends on Phase 1 declared operational.

**Goal:** Replace the manual JSONL-to-Neon ingest with a proper HTTP API that the AspireACE BFF calls. Add a SQLite-backed catalog of approved content. Single-tenant (only AspireACE BFF talks to it). Internal-only, accessed via Cloudflare Tunnel or Tailscale.

**Why now:** Once Phase 1 is producing reliable content weekly, the manual ingest step becomes friction. API also enables on-demand generation (e.g., student asks a doubt → BFF calls `/generate/explanation` live → response cached back).

**Why not earlier:** Building an API before Phase 1 proves content quality = decoration. You need approved content to serve before serving means anything.

**M2 deliverables:**
- `src/aspireace_mocf/api/` module with FastAPI server
- Routes: `/generate/{lane}`, `/content/{lane}`, `/pipeline/run`, `/pipeline/status`, `/review/approve`
- Bearer-token auth (single key shared between factory and AspireACE BFF)
- `src/aspireace_mocf/storage/sqlite_store.py` — searchable catalog of approved content
- Schema migrations for the catalog DB
- `tests/integration/test_api_phase2.py` — full API coverage
- `serving/` deployment guide: Cloudflare Tunnel setup, systemd service, FastAPI behind Caddy/Nginx
- `docs/PHASE_2_API_REFERENCE.md` — OpenAPI spec + curl examples
- AspireACE-side: `apps/bff/factory_client.py` module (lives in main repo, not here)

**M2 transition criteria (Phase 2 declared operational):**
- ✅ AspireACE BFF can hit `GET /content/notes?chapter=X` and receive approved notes
- ✅ AspireACE BFF can hit `POST /generate/explanation` and receive an on-demand explanation
- ✅ API uptime tracked (basic Prometheus-style /health + /metrics endpoint)
- ✅ Auth tested with both valid + invalid tokens
- ✅ Pre-existing AspireACE Neon content (from Phase 1 manual ingest) still works — no regression
- ✅ At least one AspireACE app surface (notes library) reads via API in production

---

## Phase 3 — Trained tutor LLM + serving

**Status:** NOT STARTED. Depends on Phase 2 operational + sufficient training data accumulated.

**Goal:** Fine-tune Qwen3-8B (or a smaller model that fits 5060 8GB / cheap rented GPU) on the tutor_app + base_subject + content_generator lanes' approved records. Serve the trained model via vLLM with OpenAI-compatible API. AspireACE BFF (and 3rd parties later) swap from Anthropic to your tutor by changing one URL.

**Trigger condition (not date-based):**
- ~10,000+ SME-approved records across base_subject + tutor_app + content_generator
- ~3 months of student interaction data showing which content/explanations land
- Phase 2 API stable and at least 50 students using it daily
- A senior-teacher-authored golden eval set (~200 query/ideal-response pairs)

**Why these thresholds:** Below ~10K records, LoRA on a 7-8B model converges to noise / overfits to the few examples. Below ~3 months of student data, you don't know if your tutor's "voice" is actually better than Anthropic's for your students. The golden eval set is mandatory — without it you can't tell if v2 is better than v1.

**M3 deliverables:**
- `src/aspireace_mocf/training/` module: `data_prep.py`, `eval_harness.py`, `golden_set.py`, `model_registry.py`
- `training_scripts/` hardened with proper docstrings, arg validation, GPU sizing guide
- `serving/` with vLLM config, OpenAI-compat shim, Dockerfile.serving, deployment runbook
- `src/aspireace_mocf/api/routes/tutor.py` — `POST /tutor/v1/chat/completions`
- Eval pipeline: trained model vs golden set, scored per dimension (correctness, pedagogy, source grounding, app usefulness)
- `docs/PHASE_3_TRAINING_GUIDE.md` + `docs/PHASE_3_SERVING_GUIDE.md`
- `eval/golden_sets/v1/` — first golden set authored by senior teachers

**M3 transition criteria (Phase 3 declared operational):**
- ✅ One LoRA training run completed end-to-end (data prep → train → eval → register)
- ✅ Trained model scores at or above prompt-chained Anthropic baseline on golden eval set
- ✅ vLLM serves the trained model with stable latency (<2s p95 for 200-token responses)
- ✅ `/tutor/v1/chat/completions` accepts OpenAI SDK calls and returns valid OpenAI-compat responses
- ✅ AspireACE BFF can toggle `JARVIS_TUTOR_BACKEND=factory_tutor_v1` and route doubt-solve to the trained model
- ✅ A/B test: 50% of doubt-solves on AspireACE go to Anthropic, 50% to factory_tutor_v1, student-feedback parity or better

---

## Phase 4 — Multi-tenant productized platform

**Status:** NOT STARTED. Depends on Phase 3 operational + commercial intent decided.

**Goal:** Transform the factory from "internal tool for AspireACE" into a commercial API platform. Sell content + tutor LLM API access to other edtech players, coaching centres, schools.

**Trigger condition:**
- Phase 3 model is genuinely better than commodity LLMs on subject-specific tasks (proven via golden eval)
- AspireACE has product-market fit (sustainable revenue, retention metrics)
- Inbound interest from at least 2-3 prospective customers (other coaching brands, schools, edtech platforms)
- Founder decides to commercialize (not blocked by capacity; this is a business call)

**Why this is far away:** Phase 4 is a different business model — you're selling APIs, not subscriptions. The unit economics, sales motion, support load, SLA commitments are different. Don't enter Phase 4 until you've earned the right to.

**M4 deliverables:**
- `src/aspireace_mocf/storage/postgres_store.py` — multi-tenant catalog
- `src/aspireace_mocf/api/auth.py` — multi-tenant API keys with per-tenant scopes
- `src/aspireace_mocf/api/middleware/rate_limit.py` — per-tenant + per-endpoint quotas
- `src/aspireace_mocf/api/middleware/usage_tracking.py` — for billing
- `src/aspireace_mocf/api/routes/admin.py` — tenant CRUD, usage reports, quota mgmt
- API versioning (v1, v2 — clients pin)
- Billing integration (Stripe / Razorpay)
- SLA monitoring + alerting (PagerDuty + Datadog or equivalent)
- Multi-region serving plan (if latency matters for global customers)
- Tenant onboarding runbook
- `docs/PHASE_4_MULTI_TENANT.md` — productization playbook

**M4 transition criteria (Phase 4 declared operational):**
- ✅ At least one paying external tenant (not AspireACE) actively using the API
- ✅ Per-tenant usage reports + invoicing automated
- ✅ Rate limits enforced and tested under load
- ✅ Versioned API with v1 stable contract; deprecation policy documented
- ✅ SLA monitoring active, on-call rotation defined

---

## Decision matrix — should we transition phases?

Use this when deciding if you're ready to start the next milestone.

| Question | If yes → ready for M2 | If yes → ready for M3 | If yes → ready for M4 |
|---|---|---|---|
| Is Phase 1 content actually landing in the app + helping students? | ✅ | — | — |
| Are teachers submitting source consistently (weekly, not one-off)? | ✅ | — | — |
| Is SME review queue keeping pace with generation? | ✅ | — | — |
| Manual ingest causing real friction (forgotten runs, errors, drift)? | ✅ | — | — |
| Have you accumulated ~10K+ SME-approved tutor/base records? | — | ✅ | — |
| Do you have a golden eval set authored by senior teachers? | — | ✅ | — |
| Is AspireACE in broad beta or live (not pre-beta)? | — | ✅ | — |
| Have you got a GPU plan (5060 + QLoRA, or rented A10G+) for training? | — | ✅ | — |
| Is your tutor v1 demonstrably better than Anthropic on subject tasks? | — | — | ✅ |
| Do you have 2+ external customers asking to pay for API access? | — | — | ✅ |
| Are AspireACE unit economics sustainable (you're not subsidizing API to survive)? | — | — | ✅ |

If you can't tick most of the relevant questions, **don't transition**. Stay in the current phase, iterate, accumulate signal.

---

## Anti-pattern: skipping phases

Tempting to want to skip straight to Phase 3 or 4 because they sound more impressive. Don't.

- **Skip Phase 1 → Phase 2:** You'll build an API with no content to serve. Empty API endpoints. The whole point of an API is to give clients something valuable; without Phase 1's approved content, you have nothing to give.
- **Skip Phase 2 → Phase 3:** You'll train a model on data that hasn't been validated by SME review. Bad signal → bad model. Even worse: no API means no easy way to swap the trained model in/out for A/B testing.
- **Skip Phase 3 → Phase 4:** You'll sell APIs that wrap commodity LLMs (Anthropic, OpenAI). Customers will figure out they can call those LLMs directly. Your moat is the trained model + content; without Phase 3 you have no moat.

The right cadence is "earn each phase" — each one delivers value on its own, and each next phase compounds on the work of the previous.

---

## Indicative timeline (illustrative, not committed)

These are rough envelopes assuming you operate the factory consistently. Real timelines depend on teacher consistency, content quality, student engagement, etc.

| Phase | Optimistic | Realistic | Pessimistic |
|---|---|---|---|
| Phase 1 → Phase 2 transition | 6 weeks | 3 months | 6 months |
| Phase 2 → Phase 3 transition | 4 months | 8 months | 14 months |
| Phase 3 → Phase 4 transition | 8 months | 18 months | 36 months (or never) |

**Phase 4 may legitimately never happen.** If AspireACE is the only customer that needs this kind of factory, that's fine. You don't have to productize it to extract value from it.

---

*Update this file when phase status changes (a milestone closes, a transition criterion is met, a phase is reframed). Not for every code edit.*
