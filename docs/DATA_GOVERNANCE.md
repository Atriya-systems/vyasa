# Data Governance

## Trainable data rule

A record is trainable only when:

```json
"train_allowed": true
```

and:

```json
"quality_status": "sme_verified"
```

## API model output rule

API model outputs are drafts. They require human/SME/internal approval before export.

## Reference material rule

Reference-only material may guide coverage but cannot be copied or used as direct training text.
