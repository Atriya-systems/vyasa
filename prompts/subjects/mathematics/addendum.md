## Mathematics-specific guidance

This addendum is concatenated to the base prompt when `SUBJECT=Mathematics`.

**JEE-only subject** — mathematics is not in NEET. `exam_targets` should be
`["JEE"]` for all mathematics source units.

### LaTeX usage

Mathematics requires precise notation. Use LaTeX for ALL non-trivial expressions:

- Inline: `$f(x) = x^2 + 3x - 2$`
- Displayed: `$$\\int_0^1 x^2 \\, dx = \\frac{1}{3}$$`
- Greek letters: `\\alpha`, `\\beta`, `\\theta`, `\\pi`, `\\Delta`
- Limits: `$\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$`
- Sums: `$\\sum_{n=1}^{\\infty} \\frac{1}{n^2} = \\frac{\\pi^2}{6}$`
- Matrices: `\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}`
- Vectors: `\\vec{a}`, `\\hat{i}`, `\\mathbf{v}`

For body text where LaTeX rendering isn't certain, fall back to plain-text
notation but be explicit:

- `pi` for `π`, `theta` for `θ`, `sqrt(2)` for `√2`, `x^2` for `x²`

### Proof structure conventions

For theorems and lemmas (`unit_type=concept` with proof, or `procedure`):

Use the standard JEE/Olympiad proof template:

```
Given: <hypotheses>
To Prove: <conclusion>
Construction: <if any auxiliary points/lines/objects>
Proof:
  Step 1: <statement> ... (reason)
  Step 2: <statement> ... (reason)
  ...
  Step n: ∴ <conclusion>.
Q.E.D. (or ∎)
```

Reasons should reference specific results (e.g. "by Pythagoras", "by AA
similarity criterion", "by induction hypothesis").

### Worked-example format

For JEE problem-solving (`unit_type=procedure` or `revision_unit`):

```
Problem: <statement>
Approach: <one-line strategy>
Solution:
  Step 1: <transformation> = <intermediate>
  Step 2: <transformation> = <intermediate>
  ...
  Step n: ∴ Final Answer = <value or expression>.
Time-saver: <optional short-method or trick>
```

Always give the final answer in simplified form (lowest terms for fractions,
exact radicals for irrationals, factored polynomials).

### Common JEE math trap categories

For `misconception` and `exam_trap` lanes:

- **Domain restrictions** — students forget to check `x ≠ 0` in
  `(x² - 1)/(x - 1)` simplification.
- **Sign of square roots** — `√(x²) = |x|`, not `x`.
- **L'Hôpital misuse** — applying without verifying 0/0 or ∞/∞ form.
- **Convergence vs absolute convergence** — students miss the distinction.
- **Probability complement** — assuming P(A∪B) = P(A) + P(B) without subtracting
  P(A∩B).
- **Matrix multiplication order** — AB ≠ BA in general.
- **Determinant properties** — expanding incorrectly along rows/columns.
- **Substitution in definite integrals** — forgetting to change limits.
- **Permutations vs combinations** — when order matters vs doesn't.

### Geometric figures

Mathematics requires geometric reasoning but the factory is text-only. For
geometry:

- Describe figures by their defining elements: "ABCD is a square with side `a`;
  P is the midpoint of AB; Q is the midpoint of CD."
- Use coordinate geometry where it simplifies: "Take A = (0, 0), B = (a, 0),
  C = (a, a), D = (0, a)."
- For complex figures, reference NCERT figure numbers where applicable.

### Subject-specific `unit_type` examples

- `concept` — fundamental theorem of calculus, principle of mathematical induction
- `formula` — quadratic formula, sum of GP `S = a(r^n - 1)/(r - 1)`, binomial theorem
- `procedure` — integration by parts, solving system of linear equations by Cramer
- `trick` — short cut for `nC2` when `n` is small; Vieta's relations for sum/product of roots
- `misconception` — "if det(A) = 0 then Ax = 0 has only trivial solution" (wrong — it has infinite)
- `exam_trap` — "JEE 2020 Q14 was a definite integral that required substitution + recognition of evenness; most candidates tried direct integration"
- `instrument` — N/A (math is symbolic; no instruments needed at JEE level)
- `revision_unit` — derivative table, integral table, trig identities summary, coordinate geometry standard forms

### JEE Mains vs JEE Advanced emphasis

- **JEE-Mains Math** — multiple-choice, ~30 questions, 3-hour shared paper.
  Depth Grade 5/6. Tests pattern recognition and direct application.
- **JEE-Adv Math** — multi-correct + numerical-answer + matrix-match.
  Depth Grade 8/9. Tests deep understanding, multi-step problem solving,
  ability to combine multiple concepts.

Tag `difficulty` accordingly: most Mains problems are `medium`; Adv problems
are usually `advanced`.

### Things to AVOID in Mathematics outputs

- Use of `÷` symbol — use `/` or `\\frac{}{}` instead.
- Mixing variable names (don't use `t` for time AND parameter in the same problem).
- Implicit assumptions (always state "where defined" or "for x > 0").
- US-style notation (e.g. `[a, b]` for closed interval is fine globally; but
  avoid `lcm` lowercase — use `LCM` per JEE convention).
- Calculus problems labeled `basic` — calculus is at minimum `medium`.
- Indian-specific cultural problems unless the math is the point.
