"""
=============================================================================
THE ONLY FILE YOU NEED TO EDIT TO MATCH YOUR REPO.

Map your existing endpoints, DB helpers and payload builders here once; the
flow helper and all 11 tests then work unchanged.
=============================================================================
"""
import pytest

# --------------------------------------------------------------------------- 1. ENDPOINTS
try:
    from constants.endpoints import (FACILITY_INTEGRATION,          # noqa: F401
                                     PRACTICE_INTEGRATION,          # noqa: F401
                                     PRACTITIONER_INTEGRATION)      # noqa: F401
except ImportError:                                                 # pragma: no cover
    PRACTITIONER_INTEGRATION = "/api/v1/practitioner/integration"
    PRACTICE_INTEGRATION     = "/api/v1/practice/integration"
    FACILITY_INTEGRATION     = "/api/v1/facility/integration"


# --------------------------------------------------------------------------- 2. DB / RESPONSE HELPERS
from utils.db_utils import get_payload_response, validate_process_status   # noqa: E402,F401
from utils.response_utils import collect_response                          # noqa: E402,F401
from utils.symplr_utils import validate_symplr_data                        # noqa: E402,F401


# --------------------------------------------------------------------------- 3. PAYLOAD BUILDERS
from test_data.practitioner_payloads import (                    # noqa: E402
    Phase_3_demoadd_update_remains_entity,
)
# Add your real builders below as they become available.
# Anything left as None makes the matching test SKIP with a clear message.

PAYLOAD_BUILDERS = {
    # ---------------- practitioner ----------------
    "phase3_demo_add_update":                 Phase_3_demoadd_update_remains_entity,
    "phase3_demographics_only":               None,
    "phase3_full_with_practice":              None,
    "practitioner_no_primary_location":       None,
    "practitioner_multiple_primary_locations": None,
    "practitioner_overlapping_contracts":     None,
    "practitioner_missing_pod_for_pcp":       None,
    "practitioner_clean_golden":              None,

    # ---------------- practice ----------------
    "practice_location_product_date_from_null": None,
    "practice_fqhc_rhc_not_pcp_with_ipa":       None,

    # ---------------- facility ----------------
    "facility_missing_effective_date":        None,
}


def build_payload(name: str) -> dict:
    """Return a fresh payload for the named scenario, or skip the test if unavailable."""
    if name not in PAYLOAD_BUILDERS:
        pytest.fail(f"Unknown payload builder '{name}'. "
                    f"Add it to PAYLOAD_BUILDERS in pdqa_adapters.py")
    builder = PAYLOAD_BUILDERS[name]
    if builder is None:
        pytest.skip(f"Payload builder '{name}' is not wired yet "
                    f"(set it in PAYLOAD_BUILDERS in pdqa_adapters.py)")
    payload = builder()
    if not isinstance(payload, dict):
        pytest.fail(f"Payload builder '{name}' returned {type(payload).__name__}, expected dict")
    return payload
