from pathlib import Path
from aspireace_mocf.validators.rights_validator import load_rights_ledger, validate_source_for_lane


def test_rights_ledger_sample_allows_base():
    ledger = load_rights_ledger(Path("examples/source_ledger.csv"))
    ok, reason = validate_source_for_lane(ledger, "SME_PHY11_CH01_001", "base_subject")
    assert ok, reason
