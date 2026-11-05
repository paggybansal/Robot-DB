"""Markers + end-of-run summary for the PDQA -> Facets reconciliation."""
import pandas as pd

from e2e_excel import SHARED_DIR
from verify import RESULTS


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: PDQA -> Facets end-to-end reconciliation")


def pytest_sessionfinish(session, exitstatus):
    if not RESULTS:
        return

    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    out = SHARED_DIR / "e2e_verification_result.xlsx"
    df = pd.DataFrame(RESULTS)

    try:
        df.to_excel(out, index=False)
        written = str(out)
    except Exception as exc:                       # file open in Excel, permissions, etc.
        written = f"<could not write: {exc}>"

    passed = int((df["RESULT"] == "PASS").sum())
    width = 110

    print("\n" + "=" * width)
    print(f" PDQA -> FACETS RECONCILIATION : {passed}/{len(df)} PASSED")
    print("=" * width)
    for _, r in df.iterrows():
        flag = "PASS" if r["RESULT"] == "PASS" else "FAIL"
        print(f" [{flag}] {r['GROUP']:<13} {r['RULE ID']:<10} NPI={r['NPI']:<12} {r['REMARKS']}")
    print("=" * width)
    print(f" Summary written to: {written}\n")
