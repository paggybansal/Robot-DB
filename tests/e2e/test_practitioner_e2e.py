"""Practitioner PDQA integration tests that hand their outcome to the Facets suite."""
import pytest

from pdqa_adapters import PRACTITIONER_INTEGRATION, build_payload
from pdqa_flow import handoff, run_pdqa_flow

GROUP = "PRACTITIONER"
pytestmark = [pytest.mark.regression, pytest.mark.practitioner_e2e]


# ===========================================================================
# 1. Demographics + Specialty (practice removed)   [your original test]
# ===========================================================================
def test_practitioner_integration_demographics_specialty(api_client, record_fallout):
    scenario = "practitioner_demographics_specialty_no_practice"

    payload = build_payload("phase3_demo_add_update")
    payload.pop("practice", None)
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)
    handoff(record_fallout, flow)


# ===========================================================================
# 2. Demographics only (no specialty, no practice)
# ===========================================================================
def test_practitioner_integration_demographics_only(api_client, record_fallout):
    scenario = "practitioner_demographics_only"

    payload = build_payload("phase3_demographics_only")
    for key in ("practice", "specialty", "transactionID"):
        payload.pop(key, None)

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)
    handoff(record_fallout, flow)


# ===========================================================================
# 3. Full payload with practice - GNPI + TaxID must be present
# ===========================================================================
def test_practitioner_integration_full_payload_with_practice(api_client, record_fallout):
    scenario = "practitioner_full_payload_with_practice"

    payload = build_payload("phase3_full_with_practice")
    payload.pop("transactionID", None)
    assert payload.get("practice"), "This scenario requires a practice block in the payload"

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)

    assert flow.ids["gnpi"], ("GNPI not found - the Facets match will fall back to NPI only. "
                              "Add the correct key to GNPI_KEYS in fallout_extract.py")
    assert flow.ids["taxid"], ("TAXID not found - add the correct key to TAXID_KEYS "
                               "in fallout_extract.py")

    handoff(record_fallout, flow)


# ===========================================================================
# 4. BRP_0021 - no primary location per GNPI/TIN
# ===========================================================================
@pytest.mark.fallout
def test_practitioner_brp_0021_no_primary_location(api_client, record_fallout):
    scenario = "practitioner_brp_0021_no_primary_location"

    payload = build_payload("practitioner_no_primary_location")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)
    handoff(record_fallout, flow,
            expected_rules=["BRP_0021"], require_rules=True,
            expected_status="INACTIVE")


# ===========================================================================
# 5. BRP_0022 - more than one primary location per GNPI/TIN
# ===========================================================================
@pytest.mark.fallout
def test_practitioner_brp_0022_multiple_primary_locations(api_client, record_fallout):
    scenario = "practitioner_brp_0022_multiple_primary_locations"

    payload = build_payload("practitioner_multiple_primary_locations")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)
    handoff(record_fallout, flow,
            expected_rules=["BRP_0022"], require_rules=True,
            expected_status="INACTIVE")


# ===========================================================================
# 6. BRP_0036 - overlapping contract dates
# ===========================================================================
@pytest.mark.fallout
def test_practitioner_brp_0036_overlapping_contracts(api_client, record_fallout):
    scenario = "practitioner_brp_0036_overlapping_contracts"

    payload = build_payload("practitioner_overlapping_contracts")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)
    handoff(record_fallout, flow,
            expected_rules=["BRP_0036"], require_rules=True,
            expected_status="INACTIVE")


# ===========================================================================
# 7. BRP_0037 - missing POD for PCP; cannot auto-resolve -> stays ACTIVE
# ===========================================================================
@pytest.mark.fallout
def test_practitioner_brp_0037_missing_pod_stays_active(api_client, record_fallout):
    scenario = "practitioner_brp_0037_missing_pod_stays_active"

    payload = build_payload("practitioner_missing_pod_for_pcp")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)
    handoff(record_fallout, flow,
            expected_rules=["BRP_0037"], require_rules=True,
            expected_status="ACTIVE")           # <-- unresolved fallout stays ACTIVE


# ===========================================================================
# 8. Clean golden payload - must NOT appear in the Facets exception report
# ===========================================================================
def test_practitioner_clean_payload_absent_from_exception_report(api_client, record_fallout):
    scenario = "practitioner_clean_golden_payload"

    payload = build_payload("practitioner_clean_golden")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTITIONER_INTEGRATION, payload, scenario, GROUP)
    handoff(record_fallout, flow, expect_clean=True)
