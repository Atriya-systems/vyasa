"""Vyasa CMS — content lifecycle management on top of factory output.

M4 addition. Replaces what was a Streamlit-only review tool in M1 with a real
content-lifecycle system per canonical inventory v3.1 §Q.

The CMS owns the state of every produced record across its full lifecycle:

    draft → machine_validated → sme_reviewed → senior_approved → published
              ↘                                                     ↘
                       flagged ─────────────────────────────────→ retired

Modules:
- storage: SQLite-backed catalog of every record + state + provenance
- state_machine: enforced transitions + per-actor authorization
- version_history: per-record immutable snapshots with diff helper
- comments: threaded review comments per record
- flags: typed accuracy-flag system (factual / pedagogical / formula / language / etc.)
- queues: needs-review queues with assignment + SLA tracking
- dashboard: aggregate metrics for content ops
- rollback: batch-level rollback with audit log
- rubrics: per-content-type review rubrics (YAML files at cms/rubrics/)

The CMS is OPTIONAL — Phase 1 batch generation works without it. Activated
when the operator calls ``aspireace-mocf cms-register`` after a run, OR via
the Streamlit review_app which auto-registers approvals.

Owner: ATRIYA / Vyasa
Version: 1.0.0 (M4)
"""
