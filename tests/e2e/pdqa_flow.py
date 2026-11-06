"""Shared PDQA execution flow + handoff to the Facets reconciliation suite."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from fallout_extract import extract_identifiers, extract_rule_ids
from pdqa_adapters import (collect_response, get_payload_response,
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
    ids: dict = field(default_factory=dict)
    rule_ids: list = field(default_factory=list)

    @property
    def has_fallout(self) -> bool:
        return bool(self.rule_ids)

    @property
    def is_error(self) -> bool:
        return str(self.process_status).strip().lower() == "error"


def run_pdqa_flow(api_client, endpoint, payload, scenario, group,
                  expect_error: bool = False, validate_symplr: bool = True) -> FlowResult:
    """Submit a payload and walk the full PDQA pipeline, printing everything."""
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

    if validate_symplr:
        flow.symplr_result = validate_symplr_data(
            business_value=payload.get("nationalProviderID"))
        _dump("SYMPLR VALIDATION", flow.symplr_result)

    flow.ids = extract_identifiers(payload, response_json, flow.symplr_result)
    flow.rule_ids = extract_rule_ids(flow.failed_messages, response_json)

    if expect_error:
        assert flow.is_error, f"{scenario}: expected process_status=error, got {flow.process_status}"
    else:
        assert not flow.is_error, f"{scenario}: integration failed - {flow.error_message}"

    return flow


def handoff(record_fallout, flow: FlowResult, *,
            expected_status: str = "INACTIVE",
            expected_rules=None,
            require_rules: bool = False,
            expect_clean: bool = False) -> list:
    """
    Hand the PDQA outcome to the Facets reconciliation suite.

    expected_rules : rules this scenario is designed to trigger
    require_rules  : fail the PDQA test if those rules did not fire
    expect_clean   : fail if ANY rule fired; record a NOT_PRESENT expectation
    """
    print("\n========== E2E HANDOFF ==========")
    print(f"SCENARIO    : {flow.scenario}")
    print(f"IDENTIFIERS : {flow.ids}")
    print(f"RULE IDS    : {flow.rule_ids or '<none - clean record>'}")

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

    if rules_to_record and not expect_clean:
        rows = record_fallout(group=flow.group, npi=flow.ids["npi"],
                              rule_ids=rules_to_record,
                              expected_status=expected_status,
                              scenario=flow.scenario, **common)
    else:
        rows = record_fallout(group=flow.group, npi=flow.ids["npi"], rule_id="",
                              expected_status="NOT_PRESENT",
                              scenario=f"{flow.scenario}_clean", **common)
        rows = [rows] if rows else []

    rows = rows or []
    print(f"RECORDED    : {len(rows)} expectation(s) for the Facets suite")
    return rows
