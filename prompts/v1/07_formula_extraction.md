You are extracting STRUCTURED FORMULA RECORDS from a Vyasa source unit. The unit already lists `formulas` as plain LaTeX expressions; your job is to convert each into a full formula record with plain-English statement, variable meanings, applicability conditions, a worked example, and a dimensional consistency check.

Rules:
- Output is JSON ARRAY only. Start with `[`, end with `]`. No markdown fences. No prose outside JSON.
- One record per formula in the source unit. If the unit lists no formulas, return `[]`.
- Generate up to {count} records (skip the rest if the source has more).
- All records start with `train_allowed=false` and `quality_status="draft"`.

SOURCE_UNIT:
{source_unit_json}

Output shape — a JSON array of formula records:

[
  {{
    "formula_id": "TEMP",
    "source_unit_id": "{unit_id}",
    "latex_expression": "v^2 = u^2 + 2as",
    "statement": "Final velocity squared equals initial velocity squared plus twice the product of acceleration and displacement.",
    "variables": [
      {{ "symbol": "v", "meaning": "final velocity", "unit": "m/s" }},
      {{ "symbol": "u", "meaning": "initial velocity", "unit": "m/s" }},
      {{ "symbol": "a", "meaning": "acceleration", "unit": "m/s^2" }},
      {{ "symbol": "s", "meaning": "displacement", "unit": "m" }}
    ],
    "applicability_conditions": [
      "Motion is along a straight line",
      "Acceleration is constant throughout the motion",
      "All quantities measured in the same inertial reference frame"
    ],
    "worked_example": "A car starts at 5 m/s, accelerates at 2 m/s^2, and travels 100 m. v^2 = 5^2 + 2*2*100 = 425; v = 20.6 m/s.",
    "dimensional_check": "[LT^-1]^2 = [LT^-1]^2 + [LT^-2][L] = [L^2T^-2]. Consistent.",
    "derivation_chapter_ref": "Class 11 Physics, Chapter 3 (Motion in a Straight Line)",
    "applied_in_chapters": ["Class 11 Physics Ch4 (Motion in a Plane)", "Class 11 Physics Ch7 (System of Particles)"],
    "subject": "{subject}",
    "chapter_no": {chapter_no},
    "exam_targets": {exam_targets_json},
    "priority": "must_know",
    "metadata": {{
      "lane": "formulas",
      "record_type": "formula_extraction",
      "quality_status": "draft",
      "train_allowed": false,
      "drafted_by": "api_model"
    }}
  }}
]

Allowed `priority` values: must_know | should_know | good_to_know.

Notes:
- For `dimensional_check`: use the same notation conventions as the subject addendum (Physics: [LT^-1], Maths: leave dimensionless, Chem: ignore if not applicable).
- For `worked_example`: keep concise — 1-2 sentences max.
- For `applied_in_chapters`: list 1-3 chapters where this formula is later applied.
- If the source unit has no formulas, return an empty JSON array `[]` (still valid).
