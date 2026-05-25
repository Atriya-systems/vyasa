You are drafting AspireACE CONTENT-GENERATOR SFT records.

Purpose: internal model behavior — generate app-ready notes, trick sheets, misconception cards, DPP blueprints, revision capsules, rubric blueprints.

Rules:
- Output is draft; train_allowed=false.
- Do not copy source/reference wording.
- Return valid JSON array only.

SOURCE_UNIT:
{source_unit_json}

Generate {count} records.

Object:
{{
  "messages": [
    {{"role":"user","content":"Generate app-ready content for..."}},
    {{"role":"assistant","content":"Structured content output..."}}
  ],
  "metadata": {{
    "record_id": "TEMP",
    "source_unit_id": "{unit_id}",
    "lane": "content_generator",
    "record_type": "notes_tricks_cards_dpp_revision_rubric",
    "quality_status": "draft",
    "train_allowed": false,
    "drafted_by": "api_model"
  }}
}}
