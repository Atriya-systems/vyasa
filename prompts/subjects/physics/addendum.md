## Physics-specific guidance

This addendum is concatenated to the base prompt when `SUBJECT=Physics`.

### Formula formatting

- Use plain-text dimensional notation: `[LT^-1]` for velocity dimensions,
  `[MLT^-2]` for force, `[ML^2T^-2]` for energy.
- For displayed equations, prefer simple notation that renders in any
  monospace font: `F = ma`, `v² = u² + 2as`, `E = mc²`.
- For more complex equations where LaTeX is needed, use inline `$...$`
  (e.g. `$\\vec{F} = q\\vec{v} \\times \\vec{B}$`).
- Always state units in SI unless explicitly contrasting with CGS.

### Direction and sign conventions

- Acceleration due to gravity: `g = 9.8 m/s²` (or `9.81` if precision matters).
  Take downward as positive UNLESS the problem context says otherwise; flag
  conventions explicitly.
- Right-hand rule for cross-products in EM and rotation.
- Conventional current direction (positive charge flow), explicitly noted
  when relevant to circuit problems.

### Common JEE-Advanced trap categories

When producing `misconception` and `exam_trap` lanes, prefer to surface
these high-yield trap families:

- **Relative motion** — students forget to subtract velocity vectors when
  observer is in motion.
- **Pseudo-forces** — confusion between inertial and non-inertial frames.
- **Pulley constraints** — string-inextensibility constraint missed.
- **Polarity in EMI** — Lenz's law sign errors.
- **Image formation conventions** — sign-convention for mirror/lens formula.
- **SHM phase relations** — confusion between displacement, velocity, acceleration.
- **Dimensional inconsistency** — students don't check dimensions in derived formulas.
- **Significant figures** — propagation through arithmetic operations.

### Subject-specific `unit_type` examples

The schema's allowed `unit_type` values map to physics as follows:

- `concept` — Newton's third law, principle of conservation of energy
- `formula` — `s = ut + (1/2)at²`, `PV = nRT`
- `procedure` — solving a 2D projectile problem, Kirchhoff's law analysis
- `trick` — short-method for moment-of-inertia of standard shapes
- `misconception` — "heavier objects fall faster"
- `exam_trap` — "JEE 2019 P2 Q23 used non-standard sign convention"
- `instrument` — vernier caliper, screw gauge, multimeter
- `revision_unit` — last-night-before-exam summary card

### NEET vs JEE emphasis

- **NEET-Phy** ≈ Class 11 + 12 NCERT, depth Grade 4/5
- **JEE-Mains-Phy** ≈ NCERT + standard extensions, depth Grade 6/7
- **JEE-Adv-Phy** ≈ NCERT + Irodov-class problems, depth Grade 8/9

Tag `difficulty` and `exam_targets` accordingly.

### Things to AVOID in Physics outputs

- Calculus notation in NEET-only units (NEET syllabus is mostly algebra-based; very
  limited calculus).
- Quantum / relativistic interpretations beyond Class 12 syllabus.
- Real-world examples that depend on cultural context unfamiliar to Indian students.
- US-system units (feet, pounds, Fahrenheit) — always SI.
