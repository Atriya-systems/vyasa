You are building AspireACE source units from owned/reference-guided educational source material.

Use books/CBSE/NCERT/JEE/NEET references only as coverage anchors. Do not copy their wording.

Return valid JSON array only.

Metadata:
subject="{subject}"
class_level="{class_level}"
chapter_no={chapter_no}
chapter_name="{chapter_name}"
source_id="{source_id}"
source_type="{source_type}"
exam_targets={exam_targets_json}

Each object:
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
}}

SOURCE:
<<<
{source_text}
>>>
