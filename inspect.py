"""One-off diagnostic: point it at the REAL Facets report and check it parses."""
from e2e_excel import (REPORT_FILE, TAB_BY_GROUP, list_sheets, read_excel_as_str,
                       read_sheet_metadata, resolve_sheet)

print("FILE  :", REPORT_FILE)
print("EXISTS:", REPORT_FILE.exists())
if REPORT_FILE.exists():
    print("SHEETS:", list_sheets(REPORT_FILE), "\n")

    for group, keyword in TAB_BY_GROUP.items():
        try:
            sheet = resolve_sheet(REPORT_FILE, keyword)
            meta = read_sheet_metadata(REPORT_FILE, sheet)
            df = read_excel_as_str(REPORT_FILE, sheet)
            print(f"--- {group}  ->  sheet '{sheet}'")
            print("    meta    :", meta)
            print("    columns :", list(df.columns))
            print("    rows    :", len(df))
            print(df.head(3).to_string(index=False))
            print()
        except Exception as exc:
            print(f"--- {group}: {type(exc).__name__}: {exc}\n")
