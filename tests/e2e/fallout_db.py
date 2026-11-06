"""
Normalise PDQA fallout-table rows and assert the API-vs-fallout contract.

Contract (from the PDQA design note):
    API Error   -> at least one fallout row must be ACTIVE
    API Success -> no fallout row may be ACTIVE (INACTIVE or no row is fine)
"""
from __future__ import annotations

from e2e_excel import key_norm, norm
from fallout_extract import extract_rule_ids

RULE_KEYS   = ("ruleid", "rulecode", "businessruleid", "rule", "brid", "validationrule")
STATUS_KEYS = ("status", "recordstatus", "falloutstatus", "activeflag", "isactive",
               "active", "statuscode")
NPI_KEYS    = ("npi", "nationalproviderid", "providernpi")
GNPI_KEYS   = ("gnpi", "groupnpi", "organizationnpi")
TAXID_KEYS  = ("taxid", "tin", "taxidentificationnumber")
SYMPLR_KEYS = ("symplrid", "symplrproviderid", "entityid", "sourcesystemid")

_ACTIVE_TOKENS   = {"A", "ACTIVE", "Y", "YES", "TRUE", "1", "OPEN"}
_INACTIVE_TOKENS = {"I", "INACTIVE", "N", "NO", "FALSE", "0", "CLOSED", "RESOLVED"}


# --------------------------------------------------------------------------- shape
def _as_rows(records) -> list:
    """Accept a DataFrame, a list of dicts/tuples, a single dict, or a wrapper dict."""
    if records is None:
        return []
    if hasattr(records, "to_dict"):                      # pandas DataFrame
        return records.to_dict("records")
    if isinstance(records, dict):
        for key in ("records", "rows", "data", "result", "fallout"):
            if isinstance(records.get(key), list):
                return records[key]
        return [records]
    if isinstance(records, (list, tuple)):
        return [r for r in records if r is not None]
    return [records]


def _pick(row: dict, candidates) -> str:
    wanted = set(candidates)
    for k, v in row.items():
        if str(k).lower().replace("_", "").replace(" ", "") in wanted:
            val = norm(v)
            if val:
                return val
    return ""


def _status(raw: str) -> str:
    s = key_norm(raw)
    if s in _ACTIVE_TOKENS:
        return "ACTIVE"
    if s in _INACTIVE_TOKENS:
        return "INACTIVE"
    return s or "UNKNOWN"


# --------------------------------------------------------------------------- parse
def parse_fallout_records(records) -> list:
    """-> [{'rule_id','status','npi','gnpi','taxid','symplr_id','raw'}, ...]"""
    out = []
    for row in _as_rows(records):
        if not isinstance(row, dict):
            rid = extract_rule_ids(row)
            out.append({"rule_id": rid[0] if rid else "", "status": "UNKNOWN",
                        "npi": "", "gnpi": "", "taxid": "", "symplr_id": "", "raw": row})
            continue

        rule_id = key_norm(_pick(row, RULE_KEYS))
        if not rule_id:
            found = extract_rule_ids(row)
            rule_id = found[0] if found else ""

        out.append({
            "rule_id":   rule_id,
            "status":    _status(_pick(row, STATUS_KEYS)),
            "npi":       _pick(row, NPI_KEYS),
            "gnpi":      _pick(row, GNPI_KEYS),
            "taxid":     _pick(row, TAXID_KEYS),
            "symplr_id": _pick(row, SYMPLR_KEYS),
            "raw":       row,
        })
    return out


# --------------------------------------------------------------------------- views
def rule_ids(rows, status=None) -> list:
    seen, out = set(), []
    for r in rows:
        if status and r["status"] != status:
            continue
        rid = r["rule_id"]
        if rid and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def summarise(rows) -> str:
    if not rows:
        return "<no fallout rows>"
    return " | ".join(f"{r['rule_id'] or '?'}:{r['status']}" for r in rows)


# --------------------------------------------------------------------------- contract
def assert_fallout_contract(rows, api_failed: bool, scenario: str = "") -> None:
    """API Error -> some fallout ACTIVE.  API Success -> none ACTIVE."""
    active = [r for r in rows if r["status"] == "ACTIVE"]
    tag = f"{scenario}: " if scenario else ""

    if api_failed:
        assert active, (
            f"{tag}API/process reported an ERROR but no ACTIVE fallout row exists. "
            f"Fallout table: {summarise(rows)}")
    else:
        assert not active, (
            f"{tag}API/process succeeded but {len(active)} fallout row(s) are still ACTIVE: "
            f"{', '.join(r['rule_id'] or '?' for r in active)}. "
            f"Fallout table: {summarise(rows)}")


def expected_facets_status(rows, rule_id: str) -> str:
    """Derive what the Facets report should show for this rule."""
    rid = key_norm(rule_id)
    statuses = {r["status"] for r in rows if r["rule_id"] == rid}
    if "ACTIVE" in statuses:
        return "ACTIVE"
    if "INACTIVE" in statuses:
        return "INACTIVE"
    return "NOT_PRESENT"
