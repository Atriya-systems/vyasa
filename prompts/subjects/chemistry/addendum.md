## Chemistry-specific guidance

This addendum is concatenated to the base prompt when `SUBJECT=Chemistry`.

### Reaction notation

- Use arrows: `→` for irreversible, `⇌` for equilibrium. ASCII alternative:
  `->` and `<=>`.
- For reaction conditions, place reagents/conditions above/below the arrow
  in text form: `A + B --(H+, heat)--> C`.
- State physical states where relevant: `(s)`, `(l)`, `(g)`, `(aq)`.
- For oxidation states, write Roman numerals in parentheses: `Fe(III)`,
  `Mn(VII)`.

### IUPAC nomenclature

- Always use systematic IUPAC names. Provide common name in parentheses where
  it adds clarity, e.g. `propanone (acetone)`, `2-methylpropan-2-ol (tert-butanol)`.
- Locants minimized per IUPAC priority rules.
- Stereodescriptors (R/S, E/Z, cis/trans) used where stereochemistry matters.

### Organic mechanism conventions

When producing `procedure` units for organic mechanisms:

- Describe curved-arrow movement: "lone pair on N attacks carbonyl C; π-bond
  breaks to give O⁻".
- Identify electrophile + nucleophile explicitly.
- Note rate-determining step.
- Identify intermediates (carbocation, carbanion, radical, tetrahedral intermediate, etc.).
- Identify products including stereochemistry where relevant.

### Common JEE/NEET chemistry trap categories

For `misconception` and `exam_trap` lanes:

- **Le Chatelier confusion** — direction of equilibrium shift when concentration
  vs pressure vs temperature changes.
- **Galvanic vs electrolytic cells** — sign convention of E°, direction of
  electron flow.
- **Markovnikov vs anti-Markovnikov** — peroxide effect on HBr addition.
- **Resonance vs tautomerism** — students often conflate these.
- **Aromaticity (4n+2 rule)** — counting π electrons in fused / heterocyclic rings.
- **Coordination compound geometry** — square planar vs tetrahedral for d⁸ vs d¹⁰.
- **NCERT-only edge cases** — JEE-Mains often tests exact wording from NCERT
  inorganic chapters; flag these.

### Subject-specific `unit_type` examples

- `concept` — Le Chatelier's principle, conjugate acid-base pairs
- `formula` — Henderson-Hasselbalch `pH = pKa + log([A-]/[HA])`, Nernst equation
- `procedure` — preparing a primary amine via Gabriel synthesis; aldol condensation mechanism
- `trick` — predicting hybridization from steric number
- `misconception` — "acidic strength always correlates with electronegativity"
- `exam_trap` — "NEET 2022 distinguished between SN1 / SN2 only by solvent polarity"
- `instrument` — burette, conductometer, calorimeter
- `revision_unit` — named reactions summary, conversion tables

### NEET vs JEE emphasis

- **NEET-Chem** ≈ heavier weighting on inorganic (especially p-block, coordination),
  biomolecules, polymers.
- **JEE-Mains-Chem** ≈ balanced physical/inorganic/organic.
- **JEE-Adv-Chem** ≈ heavy on physical-chemistry numerical problems +
  organic-mechanism depth + inorganic exceptions.

### Things to AVOID in Chemistry outputs

- Wrong oxidation-state assignments — these get caught by SMEs but waste review time.
- Incorrect IUPAC names (e.g. wrong locant priority).
- Mechanism arrows that don't conserve electrons (count the curly arrows!).
- Conflating mechanism and overall reaction.
- US-style chemical naming (e.g. "methyl alcohol" instead of "methanol").
