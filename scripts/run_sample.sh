#!/usr/bin/env bash
set -euo pipefail
python -m aspireace_mocf.cli run \
  --input examples/sample_owned_source.json \
  --rights-ledger examples/source_ledger.csv \
  --run-id sample_v3 \
  --chapter-no 1 \
  --chapter-name "Units and Measurements" \
  --limit-units 3
