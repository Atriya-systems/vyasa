# Prompts — taxonomy, versioning, and subject overrides

This directory holds every LLM prompt template the factory uses. Six base
prompts cover the pipeline stages; per-subject addendums layer on top for
chemistry, biology, and mathematics.

---

## Directory layout

```
prompts/
├── README.md                  this file
├── 01_source_units.md         legacy paths — kept for back-compat (DEPRECATED)
├── 02_base_subject.md
├── 03_tutor_app.md
├── 04_content_generator.md
├── 05_app_cards.md
├── 06_judge.md
├── v1/                        current canonical prompts (v1 of the taxonomy)
│   ├── 01_source_units.md     source text → structured source units
│   ├── 02_base_subject.md     unit → base subject corpus records
│   ├── 03_tutor_app.md        unit → student-facing tutor SFT messages
│   ├── 04_content_generator.md unit → internal content-generator SFT messages
│   ├── 05_app_cards.md        unit → app content cards (notes/tricks/etc.)
│   └── 06_judge.md            LLM-judge gate for verification
├── subjects/                  per-subject addendums (optional)
│   ├── physics/
│   │   └── addendum.md
│   ├── chemistry/
│   │   └── addendum.md
│   ├── biology/
│   │   └── addendum.md
│   └── mathematics/
│       └── addendum.md
└── anchors/                   reference examples of well-formed source
    └── (per-subject anchors)
```

---

## Prompt resolution order

When the pipeline needs a prompt template for a given stage and subject, it
resolves in this order (first hit wins):

1. **`prompts/v1/<filename>.md`** — the canonical v1 base prompt.
2. **(legacy)** `prompts/<filename>.md` — only used if `v1/` doesn't exist yet.

The subject addendum (if any) is then **appended** to the resolved base prompt:

3. **`prompts/subjects/<subject>/addendum.md`** — optional. Gets concatenated
   under a `---\n## Subject-specific guidance\n` separator. If missing, base
   prompt is used unchanged.

Result: `final_prompt = base_v1 + (subject_addendum or "")`.

This composition lets subject-specific instructions ride alongside the base
prompt without forking. To override a base prompt entirely for one subject,
copy the file into `prompts/subjects/<subject>/<filename>.md` and the
resolution will prefer the subject version (future enhancement; M1 only
supports addendum-style).

---

## Versioning

`v1/` is the locked v1 of the prompt taxonomy. Once Phase 1 is shipping
content, **never edit v1 files in place** — instead:

- Copy `v1/` to `v2/`
- Make changes in `v2/`
- Update the pipeline to read from `v2/` (via env var `PROMPT_VERSION=v2` or
  similar)
- Run A/B: route some chapters through v1, some through v2, compare SME
  approval rates and downstream student engagement metrics
- When v2 is proven better, deprecate v1 (don't delete — preserves the
  ability to re-run old chapters reproducibly)

A versioned prompt taxonomy is the difference between "we improved our
prompts" and "we know exactly which prompt was used for which approved
record, and we can re-run any of them deterministically."

---

## Per-subject addendums — what to put in them

Each subject has its own quirks. The base prompts are deliberately
subject-agnostic; addendums add the subject-specific guidance:

### Physics — `prompts/subjects/physics/addendum.md`
- LaTeX-rendered formulas, dimensional analysis
- Direction conventions (sign of g, axis orientation)
- Common JEE-Advanced trap categories
- Standard units (SI preferred; CGS where applicable)

### Chemistry — `prompts/subjects/chemistry/addendum.md`
- Reaction arrows, equilibrium symbols
- IUPAC nomenclature standards
- Oxidation states, formal charges
- Organic mechanism diagrams (curved-arrow notation hints)
- NEET vs JEE chemistry emphasis differences (inorganic depth varies)

### Biology — `prompts/subjects/biology/addendum.md`
- Process flow descriptions (cellular respiration, photosynthesis, signalling)
- Anatomy + physiology terminology
- Genetics notation (genotype/phenotype, Punnett square format hints)
- Ecology + evolutionary biology framing
- NEET-only subject; no JEE overlap

### Mathematics — `prompts/subjects/mathematics/addendum.md`
- Heavy LaTeX usage for all equations
- Proof structure conventions (Given/To Prove/Construction/Proof)
- Worked-example format for JEE problem-solving
- Geometric figure descriptions (text-only diagrams)
- JEE-only subject; not in NEET syllabus

---

## When to add a NEW subject

If you ever extend beyond Phy/Chem/Bio/Math (e.g. English, Reasoning, GK for
NEET-PG or other exam types), create:

1. `prompts/subjects/<new-subject>/addendum.md` with subject-specific guidance
2. `prompts/anchors/<new-subject>-ch01-*.json` anchor source example
3. Update `examples/source_ledger.csv` to allow the subject in `approved_for`
4. Update `src/aspireace_mocf/settings/subjects.py` (Phase 2+) with the
   subject's `unit_type` enum extensions, exam_targets, etc.
5. Add the subject to `tests/integration/test_end_to_end_<subject>.py`

---

## When to UPDATE an existing prompt

Always update via versioning, never in-place edit of `v1/`:

1. `cp -r prompts/v1 prompts/v2`
2. Edit `prompts/v2/<file>.md`
3. Add a `prompts/v2/CHANGES.md` describing what changed and why
4. Switch the pipeline to `PROMPT_VERSION=v2` for new runs
5. Track A/B: do v2 records get approved at a higher rate? Do students rate
   them higher?
6. When v2 is decisively better, mark v1 deprecated in `prompts/v1/DEPRECATED.md`
7. Never delete v1 — old approved records reference it for reproducibility

---

## Schema-shape rules every prompt MUST honor

These are enforced by `validators/basic_checks.py` and `validators/schema_validator.py`:

- **Output is a JSON ARRAY** (starts with `[`), not a single object. Even if
  the prompt asks for one record, return `[{...}]`.
- **No markdown code fences** in the response. The factory strips `\`\`\`json`
  fences as a fallback but the prompt should explicitly forbid them.
- **No prose outside the JSON.** No "Here is the JSON:" preamble.
- **All required schema fields** must be present even if empty (`""`, `[]`, `{}`).
- **`train_allowed=false`** in every drafted record. The approve step is the
  only place this flips to true.
- **`drafted_by="api_model"`** in every metadata block so the rights gate can
  enforce "no api-drafted records get train_allowed=true without SME review".

If a prompt produces output that violates any of these, the verification stage
will reject the record. Logs will show which rule fired.

---

## Testing your prompt changes

When you edit a prompt:

```bash
# Run the lane against one anchor source
python -m aspireace_mocf.cli run \
  --input prompts/anchors/physics_ch01_units_measurements_anchor.json \
  --rights-ledger examples/source_ledger.csv \
  --run-id prompt_test_$(date +%s) \
  --chapter-no 1 \
  --chapter-name "Units and Measurements" \
  --limit-units 2

# Check the output
ls runs/prompt_test_*/lanes/
cat runs/prompt_test_*/lanes/notes.jsonl | head -1 | python -m json.tool

# Check verification
cat runs/prompt_test_*/reports/notes_verification_report.json
```

If `accepted` is 0 and `rejected` > 0, look at `verified/<lane>_rejected.jsonl`
to see which `errors` codes are firing. Common causes:
- `schema_mismatch` → output doesn't match the lane's JSON schema
- `text_too_short` → prompt didn't ask for enough length
- `bad_phrase_detected` → LLM leaked self-reference ("as an AI...")
- `messages_missing` → tutor/contentgen lane returned wrong shape
- `source_similarity_warning` → prompt didn't bias hard enough against copy-paste

---

*Update this README when the prompt taxonomy changes (new stage, new subject,
new version bump, new resolution-order rule).*
