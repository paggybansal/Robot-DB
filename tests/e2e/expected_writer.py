"""
PDQA side: collect the fallout records produced during a run and hand them to the
Facets reconciliation suite as expected_records.xlsx.

Columns: GROUP | SYMPLR ID | TAXID | NPI | GNPI | RULE ID | EXPECTED STATUS |
         SCENARIO | PDQA RUN TIME | RUN ID | ENV | PDQA TEST
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import rules as rule_catalog
from e2e_excel import (EXPECTED_COLUMNS, EXPECTED_FILE, TAB_BY_GROUP,
                       key_norm, load_expected_records, norm)

EXTRA_COLUMNS = ["RUN ID", "ENV", "PDQA TEST"]
ALL_COLUMNS = EXPECTED_COLUMNS + EXTRA_COLUMNS

VALID_GROUPS = {g.upper() for g in TAB_BY_GROUP}
VALID_STATUSES = {"ACTIVE", "INACTIVE", "NOT_PRESENT"}

NPI_RE = re.compile(r"^\d{10}$")
TAXID_RE = re.compile(r"^\d{9}$")

_HEAD_FILL = PatternFill("solid", fgColor="1F3864")


class ExpectedRecordError(ValueError):
    """Raised when a test records a fallout entry the Facets side could never match."""


class ExpectedRecords:
    """Accumulates fallout expectations during a pytest session."""

    def __init__(self, run_id: str = "", env: str = "", strict: bool = True,
                 archive: bool = True, allow_unknown_rules: bool = False):
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.env = (env or "").upper()
        self.strict = strict
        self.archive = archive
        self.allow_unknown_rules = allow_unknown_rules
        self.rows: list = []
        self._seen: set = set()
        self.skipped_duplicates = 0

    # ------------------------------------------------------------------ add
    def add(self, group: str, npi: str, rule_id: str = "", *,
            gnpi: str = "", taxid: str = "", symplr_id: str = "",
            expected_status: str = "INACTIVE", scenario: str = "",
            pdqa_test: str = ""):
        group = key_norm(group) or rule_catalog.group_of(rule_id)
        rule_id = key_norm(rule_id)
        npi, gnpi, taxid = norm(npi), norm(gnpi), norm(taxid)
        symplr_id = norm(symplr_id)
        expected_status = key_norm(expected_status) or "INACTIVE"

        self._validate(group, npi, gnpi, taxid, rule_id, expected_status)

        key = (group, npi, gnpi, taxid, rule_id, expected_status)
        if key in self._seen:
            self.skipped_duplicates += 1
            return None
        self._seen.add(key)

        row = {
            "GROUP":           group,
            "SYMPLR ID":       symplr_id,
            "TAXID":           taxid,
            "NPI":             npi,
            "GNPI":            gnpi,
            "RULE ID":         rule_id,
            "EXPECTED STATUS": expected_status,
            "SCENARIO":        norm(scenario),
            "PDQA RUN TIME":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "RUN ID":          self.run_id,
            "ENV":             self.env,
            "PDQA TEST":       norm(pdqa_test),
        }
        self.rows.append(row)
        return row

    def add_rules(self, group: str, npi: str, rule_ids, **kwargs) -> list:
        return [r for r in (self.add(group, npi, rid, **kwargs) for rid in rule_ids) if r]

    # ------------------------------------------------------------------ validation
    def _validate(self, group, npi, gnpi, taxid, rule_id, expected_status):
        problems = []
        not_present = expected_status == "NOT_PRESENT"

        if group not in VALID_GROUPS:
            problems.append(f"GROUP '{group}' is not one of {sorted(VALID_GROUPS)}")
        if not npi:
            problems.append("NPI is mandatory - it is the primary match key")
        elif not NPI_RE.match(npi):
            problems.append(f"NPI '{npi}' is not 10 digits")
        if gnpi and not NPI_RE.match(gnpi):
            problems.append(f"GNPI '{gnpi}' is not 10 digits")
        if taxid and not TAXID_RE.match(taxid):
            problems.append(f"TAXID '{taxid}' is not 9 digits")

        if not rule_id:
            if not not_present:
                problems.append("RULE ID is mandatory unless EXPECTED STATUS is NOT_PRESENT")
        elif rule_catalog.get(rule_id) is None:
            msg = (f"RULE ID '{rule_id}' is not in rules.py "
                   f"(known: {', '.join(rule_catalog.known_ids())})")
            if self.allow_unknown_rules:
                print(f"[PDQA-E2E][WARN] {msg}")
            else:
                problems.append(msg)
        elif group and rule_catalog.group_of(rule_id) != group:
            problems.append(f"RULE ID '{rule_id}' belongs to "
                            f"{rule_catalog.group_of(rule_id)}, not {group}")

        if expected_status not in VALID_STATUSES:
            problems.append(f"EXPECTED STATUS '{expected_status}' not in {sorted(VALID_STATUSES)}")

        if problems:
            msg = "Invalid expected record:\n  - " + "\n  - ".join(problems)
            if self.strict:
                raise ExpectedRecordError(msg)
            print(f"[PDQA-E2E][WARN] {msg}")

    # ------------------------------------------------------------------ save
    def save(self, path=None, append: bool = False, publish_dir=None) -> Path:
        path = Path(path or EXPECTED_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = list(self.rows)
        if append and path.exists():
            existing = load_expected_records(path)
            merged, seen = [], set()
            for r in existing + rows:
                key = (key_norm(r.get("GROUP")), norm(r.get("NPI")), norm(r.get("GNPI")),
                       norm(r.get("TAXID")), key_norm(r.get("RULE ID")),
                       key_norm(r.get("EXPECTED STATUS")))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(r)
            rows = merged

        wb = Workbook()
        ws = wb.active
        ws.title = "Expected"
        ws.append(ALL_COLUMNS)
        for c in range(1, len(ALL_COLUMNS) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = _HEAD_FILL
            cell.alignment = Alignment(vertical="center")
        for r in rows:
            ws.append([str(r.get(c, "")) for c in ALL_COLUMNS])

        widths = {"GROUP": 15, "SYMPLR ID": 13, "TAXID": 13, "NPI": 13, "GNPI": 13,
                  "RULE ID": 11, "EXPECTED STATUS": 17, "SCENARIO": 38,
                  "PDQA RUN TIME": 20, "RUN ID": 18, "ENV": 8, "PDQA TEST": 50}
        for i, col in enumerate(ALL_COLUMNS, start=1):
            ws.column_dimensions[get_column_letter(i)].width = widths.get(col, 16)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(ALL_COLUMNS))}{ws.max_row}"
        wb.save(path)

        if self.archive:
            arc_dir = path.parent / "archive"
            arc_dir.mkdir(exist_ok=True)
            shutil.copy2(path, arc_dir / f"expected_records_{self.run_id}.xlsx")

        if publish_dir:
            pub = Path(publish_dir)
            pub.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, pub / path.name)
            print(f"[PDQA-E2E] published -> {pub / path.name}")

        print(f"[PDQA-E2E] wrote {len(rows)} expected record(s) -> {path}")
        return path

    # ------------------------------------------------------------------ summary
    def summary(self) -> dict:
        by_group, by_rule, by_status, by_test = {}, {}, {}, {}
        for r in self.rows:
            by_group[r["GROUP"]] = by_group.get(r["GROUP"], 0) + 1
            by_rule[r["RULE ID"] or "<none>"] = by_rule.get(r["RULE ID"] or "<none>", 0) + 1
            by_status[r["EXPECTED STATUS"]] = by_status.get(r["EXPECTED STATUS"], 0) + 1
            by_test[r["PDQA TEST"]] = by_test.get(r["PDQA TEST"], 0) + 1
        return {"total": len(self.rows), "by_group": by_group,
                "by_rule": dict(sorted(by_rule.items())),
                "by_status": by_status, "by_test": by_test,
                "duplicates_skipped": self.skipped_duplicates}
