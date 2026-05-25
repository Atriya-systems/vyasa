You are drafting AspireACE app content cards.

Generate {count} app content cards for lane "{lane}".

Rules:
- Output is draft; train_allowed=false.
- Do not copy source/reference wording.
- Use the specified surface.
- Return valid JSON array only.

SOURCE_UNIT:
{source_unit_json}

Object:
{{
  "card_id": "TEMP",
  "source_unit_id": "{unit_id}",
  "card_type": "{card_type}",
  "surface": "{surface}",
  "title": "",
  "body": "",
  "metadata": {{
    "lane": "{lane}",
    "quality_status": "draft",
    "train_allowed": false,
    "drafted_by": "api_model"
  }}
}}
