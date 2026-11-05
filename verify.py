"""Matching + verification logic for one expected PDQA record against the Facets report."""
import pandas as pd

from e2e_excel import key_norm

# Columns used to tie a PDQA record to a Facets report row.
# A blank value in the expected file means "ignore this key".
MATCH_KEYS = ["NPI", "GNPI", "TAXID"]

# Columns the report must have for verification to be possible.
REQUIRED = ["NPI", "RULE ID", "STATUS"]

RESULTS = []          # filled by the test, dumped to Excel by conftest


def find_matches(expected_row: dict, report_df: pd.DataFrame) -> pd.DataFrame:
    """All report rows matching the populated MATCH_KEYS of the expected record."""
    mask = pd.Series(True, index=report_df.index)
    used = []
    for key in MATCH_KEYS:
        value = key_norm(expected_row.get(key, ""))
        if value and key in report_df.columns:
            mask &= report_df[key].map(key_norm) == value
            used.append(key)
    if not used:
        return report_df.iloc[0:0]
    return report_df[mask]


def describe(row) -> str:
    return (f"SYMPLR ID={row.get('SYMPLR ID', '')} | RULE ID={row.get('RULE ID', '')} | "
            f"STATUS={row.get('STATUS', '')} | UPDATE DATE={row.get('UPDATE DATE', '')} | "
            f"SYMPLR CHANGED DT={row.get('SYMPLR CHANGED DT', '')} | "
            f"AUDIT NOTES={row.get('AUDIT NOTES', '')}")


def verify_record(expected_row: dict, report_df: pd.DataFrame) -> dict:
    """Return {'status': PASS|FAIL, 'remarks': str, 'actual': str} for one expected record."""
    missing = [c for c in REQUIRED if c not in report_df.columns]
    if missing:
        return {"status": "FAIL", "actual": "",
                "remarks": (f"Report sheet is missing column(s) {missing}. "
                            f"Columns present: {list(report_df.columns)}")}

    matches = find_matches(expected_row, report_df)

    if matches.empty:
        return {"status": "FAIL", "actual": "",
                "remarks": (f"Record NOT FOUND in report "
                            f"(NPI={expected_row.get('NPI', '')}, "
                            f"GNPI={expected_row.get('GNPI', '')}, "
                            f"TAXID={expected_row.get('TAXID', '')})")}

    rule_id = key_norm(expected_row.get("RULE ID", ""))
    if rule_id:
        by_rule = matches[matches["RULE ID"].map(key_norm) == rule_id]
        if by_rule.empty:
            found = ", ".join(sorted(set(matches["RULE ID"]))) or "<none>"
            return {"status": "FAIL", "actual": describe(matches.iloc[0]),
                    "remarks": f"Record present but RULE ID {rule_id} missing (rules found: {found})"}
        matches = by_rule

    row = matches.iloc[0]
    actual = describe(row)

    if len(matches) > 1:
        return {"status": "FAIL", "actual": actual,
                "remarks": f"Duplicate rows: {len(matches)} rows match the same keys + RULE ID"}

    exp_status = key_norm(expected_row.get("EXPECTED STATUS", ""))
    act_status = key_norm(row.get("STATUS", ""))
    if exp_status and exp_status != act_status:
        return {"status": "FAIL", "actual": actual,
                "remarks": f"STATUS mismatch - expected {exp_status}, got {act_status or '<blank>'}"}

    return {"status": "PASS", "actual": actual,
            "remarks": "Record found in Facets report with expected rule and status"}
