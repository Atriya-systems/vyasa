You are drafting AspireACE STUDENT-FACING TUTOR SFT records.

Purpose: app LLM behavior — doubt solving, hints, Socratic teaching, misconception repair, revision help, exam strategy.

Rules:
- Output is draft; train_allowed=false.
- Do not copy source/reference wording.
- Keep responses suitable for Class {class_level} {subject}, exam targets: {exam_targets}.
- Return valid JSON array only.

SOURCE_UNIT:
{source_unit_json}

Generate {count} records.

Object:
{{
  "messages": [
    {{"role":"user","content":"Student query..."}},
    {{"role":"assistant","content":"Tutor response..."}}
  ],
  "metadata": {{
    "record_id": "TEMP",
    "source_unit_id": "{unit_id}",
    "lane": "tutor_app",
    "record_type": "doubt_hint_misconception_revision",
    "quality_status": "draft",
    "train_allowed": false,
    "drafted_by": "api_model"
  }}
}}
