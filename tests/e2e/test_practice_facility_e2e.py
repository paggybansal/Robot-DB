"""Practice and Facility PDQA integration tests with Facets handoff."""
import pytest

from pdqa_adapters import FACILITY_INTEGRATION, PRACTICE_INTEGRATION, build_payload
from pdqa_flow import handoff, run_pdqa_flow

pytestmark = [pytest.mark.regression]


# ===========================================================================
# 9. BRG_0002 - Location Product with a null Date From
# ===========================================================================
@pytest.mark.practice_e2e
@pytest.mark.fallout
def test_practice_brg_0002_location_product_date_from_null(api_client, record_fallout):
    scenario = "practice_brg_0002_location_product_date_from_null"

    payload = build_payload("practice_location_product_date_from_null")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTICE_INTEGRATION, payload, scenario, "PRACTICE")
    handoff(record_fallout, flow,
            expected_rules=["BRG_0002"], require_rules=True,
            expected_status="INACTIVE")


# ===========================================================================
# 10. BRG_0020 - FQHC / RHC, not PCP, with IPA
# ===========================================================================
@pytest.mark.practice_e2e
@pytest.mark.fallout
def test_practice_brg_0020_fqhc_rhc_not_pcp_with_ipa(api_client, record_fallout):
    scenario = "practice_brg_0020_fqhc_rhc_not_pcp_with_ipa"

    payload = build_payload("practice_fqhc_rhc_not_pcp_with_ipa")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, PRACTICE_INTEGRATION, payload, scenario, "PRACTICE")
    handoff(record_fallout, flow,
            expected_rules=["BRG_0020"], require_rules=True,
            expected_status="INACTIVE")


# ===========================================================================
# 11. BRF_0005 - Facility product missing effective date
# ===========================================================================
@pytest.mark.facility_e2e
@pytest.mark.fallout
def test_facility_brf_0005_missing_effective_date(api_client, record_fallout):
    scenario = "facility_brf_0005_missing_effective_date"

    payload = build_payload("facility_missing_effective_date")
    payload.pop("transactionID", None)

    flow = run_pdqa_flow(api_client, FACILITY_INTEGRATION, payload, scenario, "FACILITY")
    handoff(record_fallout, flow,
            expected_rules=["BRF_0005"], require_rules=True,
            expected_status="INACTIVE")
