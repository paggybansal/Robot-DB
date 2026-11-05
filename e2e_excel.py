"""
Shared Excel helpers for the PDQA -> Facets end-to-end reconciliation.

Keep an identical copy in the PDQA repo and in the Facets repo.

Handles:
  * report sheets with a title / audit-header block above the real header row
  * sheet names that differ slightly (Practitioner vs Practitioners)
  * ids that Excel turns into floats (1234567890.0 -> 1234567890)
  * merged cells, non-breaking spaces, blank rows, repeated headers, footer notes
"""
import os
from pathlib import Path

import pandas as pd

__version__ = "2.0-header-autodetect"

# --------------------------------------------------------------------------- paths
_HERE = Path(__file__).resolve().parent

SHARED_DIR    = Path(os.getenv("E2E_SHARED_DIR", _HERE / "e2e_data"))
EXPECTED_FILE = Path(os.getenv("E2E_EXPECTED_FILE", SHARED_DIR / "expected_records.xlsx"))
REPORT_FILE   = Path(os.getenv("FACETS_REPORT", SHARED_DIR / "facets_report.xlsx"))

# --------------------------------------------------------------------------- schema
EXPECTED_COLUMNS = ["GROUP", "SYMPLR ID", "TAXID", "NPI", "GNPI",
                    "RULE ID", "EXPECTED STATUS", "SCENARIO", "PDQA RUN TIME"]

# group -> keyword used to find the sheet (case-insensitive 'contains' match)
TAB_BY_GROUP = {
    "PRACTITIONER": "practitioner",
    "PRACTICE":     "practice",
    "FACILITY":     "facility",
}

# a row is the header row when it contains at least MIN_ANCHOR_HITS of these
HEADER_ANCHORS = {"SYMPLR ID", "TAXID", "NPI", "GNPI", "RULE ID", "DESCRIPTION",
                  "UPDATE DATE", "EXPIRY DATE", "STATUS", "SYMPLR CHANGED DT",
                  "VALID FROM", "VALID TO", "AUDIT NOTES"}
MIN_ANCHOR_HITS = 3
MAX_HEADER_SCAN_ROWS = 60

REQUIRED_REPORT_COLUMNS   = {"SYMPLR ID", "NPI", "RULE ID", "STATUS"}
REQUIRED_EXPECTED_COLUMNS = {"GROUP", "NPI", "RULE ID"}

_SHEET_NAME_CACHE: dict = {}


# --------------------------------------------------------------------------- normalise
def norm(value) -> str:
    """To string, strip, drop trailing '.0' Excel adds to numeric ids, squash whitespace."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value).replace("\u00a0", " ").strip()
    if s.lower() in ("nan", "nat", "none", "<na>"):
        return ""
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return " ".join(s.split())


def key_norm(value) -> str:
    """Normalised form used only for comparisons (case-insensitive)."""
    return norm(value).upper()


def _dedupe(cols):
    seen, out = {}, []
    for c in cols:
        if c in seen:
            seen[c] += 1
            out.append(f"{c}__{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


# --------------------------------------------------------------------------- sheets
def list_sheets(path) -> list:
    return pd.ExcelFile(path).sheet_names


def resolve_sheet(path, wanted: str) -> str:
    """Exact match first, then case-insensitive 'contains' (Practitioner -> Practitioners)."""
    cache_key = (str(path), wanted.lower())
    if cache_key in _SHEET_NAME_CACHE:
        return _SHEET_NAME_CACHE[cache_key]

    names = list_sheets(path)
    w = wanted.strip().lower()

    match = next((n for n in names if n.strip().lower() == w), None)
    if match is None:
        match = next((n for n in names if w in n.strip().lower()), None)
    if match is None:
        raise ValueError(f"No sheet matching '{wanted}' in {path}. Available sheets: {names}")

    _SHEET_NAME_CACHE[cache_key] = match
    return match


# --------------------------------------------------------------------------- header
def _find_header_row(raw: pd.DataFrame) -> int:
    limit = min(len(raw), MAX_HEADER_SCAN_ROWS)
    for idx in range(limit):
        cells = {key_norm(v) for v in raw.iloc[idx].tolist() if norm(v)}
        if len(HEADER_ANCHORS & cells) >= MIN_ANCHOR_HITS:
            return idx
    raise ValueError(
        f"Could not locate the header row within the first {limit} rows. "
        f"Needed >= {MIN_ANCHOR_HITS} of {sorted(HEADER_ANCHORS)}. "
        f"Adjust HEADER_ANCHORS / MIN_ANCHOR_HITS in e2e_excel.py."
    )


def read_excel_as_str(path, sheet_name=0, required=None, key_column=None) -> pd.DataFrame:
    """
    Read a sheet as strings, skipping any title/metadata block above the real header.

    required   : set of column names that must be present (raises a readable error if not)
    key_column : column used to drop footer/blank rows. Defaults to 'SYMPLR ID' or col 0.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {path}")

    if isinstance(sheet_name, str):
        sheet_name = resolve_sheet(path, sheet_name)

    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=str).fillna("")
    hdr = _find_header_row(raw)

    columns = _dedupe([key_norm(c) for c in raw.iloc[hdr].tolist()])
    df = raw.iloc[hdr + 1:].copy()
    df.columns = columns
    df = df.loc[:, [c for c in df.columns if c]]                 # drop unnamed/blank columns

    for col in df.columns:
        df[col] = df[col].map(norm)

    df = df[~df.apply(lambda r: all(v == "" for v in r), axis=1)]        # drop blank rows

    anchor = key_column or ("SYMPLR ID" if "SYMPLR ID" in df.columns else df.columns[0])
    if anchor in df.columns:
        df = df[df[anchor] != ""]                                        # drop footer/notes
        df = df[df[anchor].str.upper() != anchor]                        # drop repeated headers

    df = df.reset_index(drop=True)

    # ------------------------------------------------- fail fast, readable messages
    if any(c.startswith("UNNAMED") for c in df.columns):
        raise RuntimeError(
            f"[e2e_excel v{__version__}] Header parsing failed for sheet '{sheet_name}' in {path}.\n"
            f"  Columns parsed : {list(df.columns)}\n"
            f"  Header detected at raw row index {hdr}.\n"
            f"  If you see UNNAMED columns, an OLD copy of e2e_excel.py is being imported "
            f"(delete __pycache__ / remove the duplicate file)."
        )

    if required:
        missing = set(required) - set(df.columns)
        if missing:
            raise RuntimeError(
                f"[e2e_excel v{__version__}] Sheet '{sheet_name}' is missing required column(s): "
                f"{sorted(missing)}.\n  Columns found: {list(df.columns)}\n"
                f"  Header detected at raw row index {hdr}."
            )

    return df


# --------------------------------------------------------------------------- metadata
def read_sheet_metadata(path, sheet_name=0) -> dict:
    """Pull the audit header ('Execution Audit Status', 'Processed Record Count') from
    the rows above the data header."""
    path = Path(path)
    if isinstance(sheet_name, str):
        sheet_name = resolve_sheet(path, sheet_name)

    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=str).fillna("")
    hdr = _find_header_row(raw)

    def grab(label: str) -> str:
        lu = label.upper()
        for i in range(hdr):
            row = [norm(v) for v in raw.iloc[i].tolist()]
            for j, cell in enumerate(row):
                if lu in cell.upper():
                    if ":" in cell and cell.split(":", 1)[1].strip():
                        return cell.split(":", 1)[1].strip()
                    for k in range(j + 1, len(row)):               # next cell, same row
                        if row[k]:
                            return row[k]
                    if i + 1 < hdr:                                 # value dropped a row
                        for v in (norm(x) for x in raw.iloc[i + 1].tolist()):
                            if v:
                                return v
        return ""

    title = next((norm(v) for i in range(hdr) for v in raw.iloc[i].tolist() if norm(v)), "")
    count = grab("Processed Record Count")

    return {
        "sheet": sheet_name,
        "title": title,
        "audit_status": grab("Execution Audit Status"),
        "processed_count": int(count) if count.isdigit() else None,
        "header_row_index": hdr,
    }


# --------------------------------------------------------------------------- loaders
def load_expected_records(path=None) -> list:
    """Read expected_records.xlsx produced by the PDQA run. Returns [] if absent."""
    path = Path(path or EXPECTED_FILE)
    if not path.exists():
        return []
    df = read_excel_as_str(path,
                           required=REQUIRED_EXPECTED_COLUMNS,
                           key_column="NPI")
    return df.to_dict("records")
