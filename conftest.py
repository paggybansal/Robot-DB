"""Markers, run metadata and report generation for the PDQA -> Facets reconciliation."""
from e2e_excel import EXPECTED_FILE, REPORT_FILE, SHARED_DIR
from report import RUN_INFO, init_run_info, summarise, write_excel, write_html
from verify import RESULTS


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: PDQA -> Facets end-to-end reconciliation")


def pytest_sessionstart(session):
    init_run_info(EXPECTED_FILE, REPORT_FILE)


def pytest_sessionfinish(session, exitstatus):
    if not RESULTS:
        return

    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    xlsx_path = SHARED_DIR / "e2e_verification_result.xlsx"
    html_path = SHARED_DIR / "e2e_report.html"

    def _safe_write(fn, path):
        try:
            return str(fn(RESULTS, path))
        except Exception as exc:        # file open in Excel / permissions
            return f"<not written: {exc}>"

    xlsx_out = _safe_write(write_excel, xlsx_path)
    html_out = _safe_write(write_html, html_path)

    s = summarise(RESULTS)
    width = 118
    print("\n" + "=" * width)
    print(f" PDQA -> FACETS RECONCILIATION   "
          f"{'PASSED' if s['failed'] == 0 else 'FAILED'}   "
          f"{s['passed']}/{s['total']} passed  ({s['pass_rate']}%)")
    print("=" * width)
    for r in RESULTS:
        flag = "PASS" if r["RESULT"] == "PASS" else "FAIL"
        print(f" [{flag}] {r.get('GROUP',''):<13} {r.get('RULE ID',''):<10} "
              f"NPI={r.get('NPI',''):<12} {r.get('REMARKS','')}")
    print("-" * width)
    for g, v in s["by_group"].items():
        print(f" {g:<14} total={v['total']:<4} pass={v['pass']:<4} fail={v['fail']}")
    if s["by_reason"]:
        print("-" * width)
        for reason, count in s["by_reason"].items():
            print(f" {reason:<22} {count}")
    print("=" * width)
    print(f" HTML report : {html_out}")
    print(f" Excel report: {xlsx_out}")
    try:
        print(f" Open        : file:///{str(html_path).replace(chr(92), '/')}")
    except Exception:
        pass
    print()
