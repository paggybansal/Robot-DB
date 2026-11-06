"""Shared PDQA execution flow + handoff to the Facets reconciliation suite."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import fallout_db
from fallout_extract import extract_identifiers, extract_rule_ids
from pdqa_adapters import (VALIDATE_FALLOUT_AGAINST_RESPONSE, collect_response,
                           get_fallout, get_payload_response,
                           validate_process_status, validate_symplr_data)


def _dump(label: str, obj):
    print(f"\n========== {label} ==========")
    try:
        print(json.dumps(obj, indent=2, default=str))
    except Exception:
        print(obj)


@dataclass
class FlowResult:
    scenario: str
    group: str
    payload: dict
    status_code: int = 0
    transaction_id: str = ""
    process_status: str = ""
    process_name: str = ""
    error_message: str = ""
    payload_response_id: str = ""
    response_json: dict = field(default_factory=dict)
    failed_messages: object = None
    symplr_result: object = None

    # ---- fallout table ----
    fallout_raw: object = None
    fallout_rows: list = field(default_factory=list)
    fallout_checked: bool = False

    # ---- derived ----
    response_rule_ids: list = field(default_factory=list)
    ids: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ views
    @property
    def fallout_rule_ids(self) -> list:
        return fallout_db.rule_ids(self.fallout_rows)

    @property
    def active_rule_ids(self) -> list:
        return fallout_db.rule_ids(self.fallout_rows, status="ACTIVE")

    @property
    def inactive_rule_ids(self) -> list:
        return fallout_db.rule_ids(self.fallout_rows, status="INACTIVE")

    @property
    def rule_ids(self) -> list:
        """Fallout table is the source of truth; DL response is the fallback."""
        return self.fallout_rule_ids or self.response_rule_ids

    @property
    def is_error(self) -> bool:
        return str(self.process_status).strip().lower() == "error"

    @property
    def has_fallout(self) -> bool:
        return bool(self.rule_ids)

    def status_for_rule(self, rule_id: str) -> str:
        if not self.fallout_checked:
            return "INACTIVE"          # no fallout reader wired -> assume resolved
        return fallout_db.expected_facets_status(self.fallout_rows, rule_id)


# =========================================================================== flow
def run_pdqa_flow(api_client, endpoint, payload, scenario, group,
                  expect_error: bool = False,
                  validate_symplr: bool = True,
                  check_fallout: bool = True) -> FlowResult:
    """Submit a payload, walk the full PDQA pipeline, validate the fallout table."""
    flow = FlowResult(scenario=scenario, group=group.upper(), payload=payload)

    print(f"\n========== {scenario.upper()} ==========")
    print(f"NPI : {payload.get('nationalProviderID', '<not in payload>')}")
    _dump("REQUEST PAYLOAD", payload)

    response = api_client.post_action(endpoint, payload)
    flow.status_code = response.status_code
    print(f"\nSTATUS CODE : {response.status_code}")
    assert response.status_code == 200, f"{scenario}: expected 200, got {response.status_code}"

    res = response.json()
    flow.transaction_id = res["transaction_id"]
    print(f"\nTRANSACTION ID : {flow.transaction_id}")

    db_status = validate_process_status(
        transaction_id=flow.transaction_id,
        expected_npi=payload.get("nationalProviderID"),
    )
    flow.process_status      = db_status.get("process_status")
    flow.process_name        = db_status.get("sub_process_name")
    flow.error_message       = db_status.get("error_message")
    flow.payload_response_id = db_status.get("payload_response_id")

    print(f"\nFINAL PROCESS STATUS : {flow.process_status}")
    print(f"COMPLETED PROCESS     : {flow.process_name}")
    if flow.error_message:
        print(f"DB ERROR MESSAGE : {flow.error_message}")

    assert flow.payload_response_id, f"{scenario}: Payload Response ID is NULL"

    db_payload = get_payload_response(flow.payload_response_id)
    response_json = db_payload.get("response", {})
    if isinstance(response_json, str):
        response_json = json.loads(response_json)
    flow.response_json = response_json
    _dump("DL RESPONSE", response_json)

    flow.failed_messages = collect_response(response_json)
    _dump("FAILED MESSAGES", flow.failed_messages)

    flow.response_rule_ids = extract_rule_ids(flow.failed_messages, response_json)

    if validate_symplr:
        flow.symplr_result = validate_symplr_data(
            business_value=payload.get("nationalProviderID"))
        _dump("SYMPLR VALIDATION", flow.symplr_result)

    # ==================================================================
    # FALLOUT TABLE VALIDATION
    #   API Error   -> Fallout must be ACTIVE
    #   API Success -> Fallout must NOT be ACTIVE (INACTIVE or none is fine)
    # ==================================================================
    if check_fallout:
        flow.fallout_raw = get_fallout(flow.group, payload.get("nationalProviderID"))

        if flow.fallout_raw is None:
            print(f"\n========== FALLOUT TABLE ==========\n"
                  f"<no reader wired for {flow.group} - see FALLOUT_GETTERS "
                  f"in pdqa_adapters.py>")
        else:
            flow.fallout_rows = fallout_db.parse_fallout_records(flow.fallout_raw)
            flow.fallout_checked = True
            _dump("FALLOUT TABLE (raw)", flow.fallout_raw)
            print(f"\nFALLOUT SUMMARY : {fallout_db.summarise(flow.fallout_rows)}")
            print(f"  ACTIVE   : {flow.active_rule_ids or '<none>'}")
            print(f"  INACTIVE : {flow.inactive_rule_ids or '<none>'}")

            # your existing cross-check, if available
            if VALIDATE_FALLOUT_AGAINST_RESPONSE is not None:
                VALIDATE_FALLOUT_AGAINST_RESPONSE(
                    fallout_records=flow.fallout_raw,
                    rules=flow.response_rule_ids,
                )

            fallout_db.assert_fallout_contract(
                flow.fallout_rows, api_failed=flow.is_error, scenario=scenario)

    flow.ids = extract_identifiers(payload, response_json, flow.symplr_result,
                                   flow.fallout_raw)

    if expect_error:
        assert flow.is_error, f"{scenario}: expected process_status=error, got {flow.process_status}"
    else:
        assert not flow.is_error, f"{scenario}: integration failed - {flow.error_message}"

    return flow


# =========================================================================== handoff
def handoff(record_fallout, flow: FlowResult, *,
            expected_status: str = None,
            expected_rules=None,
            require_rules: bool = False,
            expect_clean: bool = False) -> list:
    """
    Hand the PDQA outcome to the Facets reconciliation suite.

    expected_status : None -> derived per rule from the PDQA fallout table
    expected_rules  : rules this scenario is designed to trigger
    require_rules   : fail the PDQA test if those rules did not fire
    expect_clean    : fail if ANY rule fired; record a NOT_PRESENT expectation
    """
    print("\n========== E2E HANDOFF ==========")
    print(f"SCENARIO        : {flow.scenario}")
    print(f"IDENTIFIERS     : {flow.ids}")
    print(f"FALLOUT RULES   : {flow.fallout_rule_ids or '<none>'}")
    print(f"RESPONSE RULES  : {flow.response_rule_ids or '<none>'}")
    print(f"SOURCE USED     : {'fallout table' if flow.fallout_rule_ids else 'DL response'}")

    assert flow.ids.get("npi"), (
        f"{flow.scenario}: could not extract a 10-digit NPI for the Facets handoff. "
        f"Add the correct key name to NPI_KEYS in fallout_extract.py")

    if expected_rules and require_rules:
        missing = sorted(set(expected_rules) - set(flow.rule_ids))
        assert not missing, (
            f"{flow.scenario}: expected rule(s) {missing} did not fire in PDQA. "
            f"Rules actually raised: {flow.rule_ids or '<none>'}")

    if expect_clean:
        assert not flow.rule_ids, (
            f"{flow.scenario}: expected a clean record but PDQA raised {flow.rule_ids}")

    common = dict(gnpi=flow.ids.get("gnpi", ""),
                  taxid=flow.ids.get("taxid", ""),
                  symplr_id=flow.ids.get("symplr_id", ""))

    rules_to_record = list(expected_rules) if expected_rules else list(flow.rule_ids)
    rows = []

    if not rules_to_record or expect_clean:
        row = record_fallout(group=flow.group, npi=flow.ids["npi"], rule_id="",
                             expected_status="NOT_PRESENT",
                             scenario=f"{flow.scenario}_clean",
                             pdqa_fallout_status="NONE", **common)
        rows = [row] if row else []
        print("RECORDED        : 1 NOT_PRESENT expectation")
        return rows

    # group the rules by the status we expect Facets to show
    buckets: dict = {}
    for rid in rules_to_record:
        derived = flow.status_for_rule(rid)
        status = expected_status or (derived if derived != "NOT_PRESENT" else "INACTIVE")
        buckets.setdefault((status, derived), []).append(rid)

    for (status, derived), rids in buckets.items():
        got = record_fallout(group=flow.group, npi=flow.ids["npi"], rule_ids=rids,
                             expected_status=status,
                             scenario=flow.scenario,
                             pdqa_fallout_status=derived, **common)
        rows.extend(got or [])
        print(f"RECORDED        : {rids} -> expect {status} in Facets "
              f"(PDQA fallout: {derived})")

    return rows
