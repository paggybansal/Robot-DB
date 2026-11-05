"""
Verifies that every record PDQA wrote to expected_records.xlsx appears correctly
in the Facets audit report generated after the 2-hourly sync job.
"""
import pytest

import e2e_excel
from e2e_excel import (EXPECTED_FILE, REPORT_FILE, REQUIRED_REPORT_COLUMNS,
                       TAB_BY_GROUP, list_sheets, load_expected_records,
                       read_excel_as_str, read_sheet_metadata)
from verify import RESULTS, verify_record

# Flip on once you confirm "Processed Record Count" == number of rows in that tab
CHECK_PROCESSED_COUNT = False

EXPECTED = load_expected_records()
GROUPS_UNDER_TEST = sorted({r["GROUP"].upper() for r in EXPECTED}) if EXPECTED else []


def _test_id(r):
    return (f"{r.get('GROUP') or '?'}-"
            f"{r.get('RULE ID') or 'NORULE'}-"
            f"{r.get('NPI') or 'NONPI'}")


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def report_tabs():
    assert REPORT_FILE.exists(), (
        f"Facets report not found: {REPORT_FILE}\n"
        f"Set the FACETS_REPORT env var or drop the file in {REPORT_FILE.parent}")

    tabs = {}
    for group in GROUPS_UNDER_TEST:
        keyword = TAB_BY_GROUP.get(group)
        assert keyword, (f"Unknown GROUP '{group}' in {EXPECTED_FILE.name}. "
                         f"Allowed: {sorted(TAB_BY_GROUP)}")
        tabs[group] = read_excel_as_str(REPORT_FILE,
                                        sheet_name=keyword,
                                        required=REQUIRED_REPORT_COLUMNS)
    return tabs


@pytest.fixture(scope="session")
def report_meta():
    return {g: read_sheet_metadata(REPORT_FILE, TAB_BY_GROUP[g]) for g in GROUPS_UNDER_TEST}


# --------------------------------------------------------------------------- sanity
def test_reader_module_is_current():
    assert getattr(e2e_excel, "__version__", "") == "2.0-header-autodetect", (
        f"Stale e2e_excel loaded from {e2e_excel.__file__}. "
        f"Delete __pycache__ or remove the duplicate copy.")


def test_input_files_exist():
    assert EXPECTED_FILE.exists(), f"PDQA expectation file missing: {EXPECTED_FILE}"
    assert REPORT_FILE.exists(), f"Facets report missing: {REPORT_FILE}"
    assert EXPECTED, f"{EXPECTED_FILE.name} has no data rows"


@pytest.mark.skipif(not GROUPS_UNDER_TEST, reason="no expected records")
@pytest.mark.parametrize("group", GROUPS_UNDER_TEST)
def test_report_structure_is_parsable(group, report_tabs):
    df = report_tabs[group]
    print(f"\n[{group}] sheets={list_sheets(REPORT_FILE)} rows={len(df)} "
          f"columns={list(df.columns)}")
    assert not df.empty, f"No data rows parsed for {group}"
    assert REQUIRED_REPORT_COLUMNS.issubset(set(df.columns))


@pytest.mark.skipif(not GROUPS_UNDER_TEST, reason="no expected records")
@pytest.mark.parametrize("group", GROUPS_UNDER_TEST)
def test_report_audit_header_is_healthy(group, report_meta, report_tabs):
    meta = report_meta[group]
    print(f"\n[{group}] meta={meta}")

    status = (meta["audit_status"] or "").upper()
    assert status, f"'Execution Audit Status' not found in sheet '{meta['sheet']}'"
    assert "FAIL" not in status, f"Pipeline audit status for {group} is '{meta['audit_status']}'"
    assert ("PASSED" in status or "SYNCED" in status), \
        f"Unexpected audit status for {group}: '{meta['audit_status']}'"

    if CHECK_PROCESSED_COUNT and meta["processed_count"] is not None:
        assert meta["processed_count"] == len(report_tabs[group]), (
            f"Processed Record Count={meta['processed_count']} but sheet has "
            f"{len(report_tabs[group])} data rows")


# --------------------------------------------------------------------------- the test
@pytest.mark.e2e
@pytest.mark.skipif(not EXPECTED, reason="No expected_records.xlsx from the PDQA run")
@pytest.mark.parametrize("expected", EXPECTED, ids=[_test_id(r) for r in EXPECTED])
def test_pdqa_record_present_in_facets_report(expected, report_tabs):
    group = (expected.get("GROUP") or "").upper()
    assert group in report_tabs, f"Unknown group tab: '{group}'"

    result = verify_record(expected, report_tabs[group])

    RESULTS.append({
        "GROUP":           expected.get("GROUP", ""),
        "SCENARIO":        expected.get("SCENARIO", ""),
        "SYMPLR ID":       expected.get("SYMPLR ID", ""),
        "TAXID":           expected.get("TAXID", ""),
        "NPI":             expected.get("NPI", ""),
        "GNPI":            expected.get("GNPI", ""),
        "RULE ID":         expected.get("RULE ID", ""),
        "EXPECTED STATUS": expected.get("EXPECTED STATUS", ""),
        "PDQA RUN TIME":   expected.get("PDQA RUN TIME", ""),
        "RESULT":          result["status"],
        "REMARKS":         result["remarks"],
        "FACETS ROW":      result["actual"],
    })

    assert result["status"] == "PASS", (
        f"\n  Scenario   : {expected.get('SCENARIO', '')}"
        f"\n  Reason     : {result['remarks']}"
        f"\n  Facets row : {result['actual'] or '<none>'}")
