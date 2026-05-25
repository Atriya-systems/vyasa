## Biology-specific guidance

This addendum is concatenated to the base prompt when `SUBJECT=Biology`.

**NEET-only subject** — biology is not in JEE. `exam_targets` should be
`["NEET"]` for all biology source units.

### Process flow descriptions

For cellular and physiological processes (`unit_type=concept` or `procedure`),
describe step-by-step with intermediate states:

- Inputs (substrates, enzymes, conditions)
- Stepwise transformations (use `→` between states)
- Intermediates explicitly named
- Outputs (products, energy yield, byproducts)
- Subcellular location where relevant (cytoplasm vs mitochondria vs chloroplast etc.)

Example: "Glycolysis: glucose (cytoplasm) → glucose-6-phosphate (hexokinase, ATP) →
fructose-6-phosphate (phosphoglucose isomerase) → fructose-1,6-bisphosphate
(PFK-1, ATP) → ... → 2 pyruvate + 2 ATP + 2 NADH."

### Anatomy and physiology terminology

- Use precise anatomical terms: `proximal/distal`, `anterior/posterior`,
  `dorsal/ventral`, `medial/lateral`.
- Greek/Latin root forms preferred over colloquial (e.g. `nephron` not
  "kidney unit", `axon hillock` not "where signal starts").
- For organ-system descriptions, identify the system explicitly
  (digestive / respiratory / circulatory / excretory / nervous / endocrine /
  reproductive / immune).

### Genetics notation

- Genotype: `AABb`, `XHY`, `IAIB` (use uppercase for dominant, lowercase for
  recessive; superscript for alleles where needed).
- Phenotype: descriptive text or shorthand like `tall, round`.
- Punnett squares: describe in text form, e.g. "F1 cross AaBb × AaBb gives
  9:3:3:1 ratio of A_B_:A_bb:aaB_:aabb".
- Probabilities expressed as fractions (`3/4`) or percentages (`75%`).

### Diagram references

Biology is the most diagram-heavy subject. Since the factory is text-only in
Phase 1, do NOT attempt to draw diagrams in `body` text. Instead:

- Reference the diagram by NCERT figure number where applicable
  (e.g. "Refer to NCERT Class 11 Bio Fig 6.2 for the structure of the cell").
- For trick / formula / revision lanes where diagrams would help, describe the
  diagram's KEY LABELS in text bullets:
  - "Cell membrane labels: phospholipid bilayer, integral proteins,
    cholesterol, glycoprotein, glycolipid, peripheral protein."
- Phase 2+ adds diagram-attachment support; until then, text-only with
  explicit "diagram lives in NCERT" references.

### Common NEET biology trap categories

For `misconception` and `exam_trap` lanes:

- **Plant vs animal mitosis** — students forget cytokinesis differs
  (cell plate in plants, cleavage furrow in animals).
- **Inhibition types** — competitive vs non-competitive vs uncompetitive on
  Lineweaver-Burk plots.
- **Genetic code degeneracy** — confusing degenerate codons with overlapping reading frames.
- **Photosynthesis dark/light reactions** — students mix up the products
  (ATP/NADPH in light; G3P in Calvin cycle).
- **Hormone source vs target organ** — common to confuse where hormone is
  produced vs where it acts.
- **Taxonomy nomenclature** — italicizing genus species; capitalizing first
  letter of genus only.
- **Plant vs animal cell organelles** — chloroplasts/vacuole/cell wall vs
  centrioles/lysosomes.

### Subject-specific `unit_type` examples

- `concept` — central dogma, natural selection, homeostasis
- `formula` — Hardy-Weinberg equilibrium `p² + 2pq + q² = 1`, RQ in respiration
- `procedure` — glycolysis steps, transcription mechanism, ABO blood-group testing
- `trick` — mnemonic for cranial nerves, easy recall of pH ranges
- `misconception` — "the appendix has no function" (it has lymphoid tissue)
- `exam_trap` — "NEET 2021 distinguished sieve tubes from companion cells by
  presence of nucleus, not by cytoplasm"
- `instrument` — microscope, sphygmomanometer, ECG, electrophoresis
- `revision_unit` — taxonomy chart, Mendel summary, cell cycle phases summary

### NEET-specific syllabus boundaries

- **Class 11**: diversity in living world, structural organisation in animals/plants,
  cell structure and function, plant physiology, human physiology
- **Class 12**: reproduction, genetics and evolution, biology and human welfare,
  biotechnology, ecology and environment

Stay strictly within NCERT Class 11 + 12 Biology for `coverage_points`. Anything
beyond is out-of-syllabus and traps SMEs into rejecting the record.

### Things to AVOID in Biology outputs

- Speculation about evolution beyond NCERT framing.
- Medical advice or disease treatments (NEET is foundational biology, not clinical).
- Diagrams attempted in plain text — describe the labels instead.
- US-centric examples (e.g. "the bald eagle" — use Indian examples like the
  Indian peafowl or peacock).
- Outdated taxonomy (use the five-kingdom system unless explicitly contrasting
  with newer three-domain).
