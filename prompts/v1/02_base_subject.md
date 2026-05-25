You are drafting original BASE SUBJECT-MATTER corpus records for AspireACE.

Purpose: teach subject matter before app behavior.

Rules:
- Output is draft; train_allowed=false.
- Use only the source unit as coverage requirement.
- Do not copy source/reference wording.
- Include notes, formulas, tricks, misconceptions, exam traps, and revision-ready language where applicable.
- Return valid JSON array only.

SOURCE_UNIT:
{source_unit_json}

Generate {count} records.

Object:
{{
  "text": "Original subject-matter text...",
  "metadata": {{
    "record_id": "TEMP",
    "source_unit_id": "{unit_id}",
    "lane": "base_subject",
    "record_type": "base_note",
    "quality_status": "draft",
    "train_allowed": false,
    "drafted_by": "api_model"
  }}
}}
