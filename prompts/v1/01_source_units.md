You are building AspireACE source units from owned/reference-guided educational source material.

Use books/CBSE/NCERT/JEE/NEET references only as coverage anchors. Do not copy their wording.

Return valid JSON ARRAY only. The response MUST start with `[` and end with `]`. Do not wrap it in any other object, do not add prose, do not add markdown code fences.

Metadata:
subject="{subject}"
class_level="{class_level}"
chapter_no={chapter_no}
chapter_name="{chapter_name}"
source_id="{source_id}"
source_type="{source_type}"
exam_targets={exam_targets_json}

Output shape — a JSON array of one or more unit objects:

[
  {{
    "unit_id": "TEMP",
    "source_id": "{source_id}",
    "subject": "{subject}",
    "class_level": "{class_level}",
    "chapter_no": {chapter_no},
    "chapter_name": "{chapter_name}",
    "topic": "",
    "subtopic": "",
    "unit_name": "",
    "unit_type": "concept",
    "difficulty": "basic",
    "exam_targets": {exam_targets_json},
    "source_type": "{source_type}",
    "reference_policy": "reference_only_no_copy",
    "coverage_points": [],
    "formulas": [],
    "common_errors": [],
    "prerequisites": [],
    "next_units": [],
    "target_states": {{"grounding":"medium","fluency":"medium","flexibility":"medium","load":"medium","autonomy":"medium"}},
    "train_allowed": false
  }},
  {{
    "unit_id": "TEMP",
    "source_id": "{source_id}",
    "subject": "{subject}",
    "class_level": "{class_level}",
    "chapter_no": {chapter_no},
    "chapter_name": "{chapter_name}",
    "topic": "",
    "subtopic": "",
    "unit_name": "",
    "unit_type": "formula",
    "difficulty": "medium",
    "exam_targets": {exam_targets_json},
    "source_type": "{source_type}",
    "reference_policy": "reference_only_no_copy",
    "coverage_points": [],
    "formulas": [],
    "common_errors": [],
    "prerequisites": [],
    "next_units": [],
    "target_states": {{"grounding":"medium","fluency":"medium","flexibility":"medium","load":"medium","autonomy":"medium"}},
    "train_allowed": false
  }}
]

Allowed `unit_type` values: concept | formula | procedure | trick | misconception | exam_trap | instrument | revision_unit.
Allowed `difficulty` values: basic | medium | advanced.

SOURCE:
<<<
{source_text}
>>>
