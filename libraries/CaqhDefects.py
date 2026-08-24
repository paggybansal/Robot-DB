"""Robot keywords for the defect register."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from robot.api import logger
from robot.api.deco import keyword, library

PATH = Path(__file__).resolve().parent.parent / "resources" / "defects.yaml"


class Defect(BaseModel):
    severity: Literal["P0", "P1", "P2", "P3"]
    status: Literal["open", "fixed", "ask"]
    title: str
    question: str | None = None
    outcomes: list[int] = Field(default_factory=list)

    @property
    def summary(self) -> str:
        return " ".join(self.title.split())


@library(scope="GLOBAL", version="1.0", auto_keywords=False)
class CaqhDefects:
    """Compares what a test found against what the defect register says."""

    @staticmethod
    @lru_cache(maxsize=1)
    def _registry() -> dict[str, Defect]:
        raw = yaml.safe_load(PATH.read_text("utf-8")) or {}
        return {key: Defect(**value) for key, value in raw.items()}

    def _get(self, defect_id: str) -> Defect:
        registry = self._registry()
        if defect_id not in registry:
            raise AssertionError(
                f"'{defect_id}' is not in resources/defects.yaml.\n"
                f"Known: {', '.join(sorted(registry))}"
            )
        return registry[defect_id]

    @keyword("Findings Should Match Defect Register")
    def findings_should_match_defect_register(
        self,
        defect_id: str,
        rows: list[dict[str, Any]],
        finding: str = "",
        why: str = "",
    ) -> None:
        """Compares a result set against the register entry for ``defect_id``.

        ``rows`` non-empty means the problem is present.

        | register | rows found | outcome |
        | open     | yes        | PASS - confirmed as documented |
        | open     | no         | FAIL - appears fixed, update the register |
        | fixed    | yes        | FAIL - regression |
        | fixed    | no         | PASS - verified fixed |
        | ask      | either     | PASS with a note |

        Example:
        | ${rows}= | Run Reference Query | fan_out |
        | Findings Should Match Defect Register | DEF-008 | ${rows} |
        | ...      | finding=${count} practitioners are selected twice |
        | ...      | why=Missing DISTINCT causes duplicate CAQH submissions |
        """
        defect = self._get(defect_id)
        present = bool(rows)
        count = len(rows)
        header = f"{defect_id} [{defect.severity}] {defect.summary}"

        detail = ""
        if finding:
            detail += f"\n\nFinding:\n      {finding}"
        if why:
            detail += f"\n\nWhy it matters:\n      {why}"

        if defect.status == "ask":
            state = f"{count} row(s) found" if present else "no rows found"
            logger.warn(
                f"{header}\n\nAwaiting a business answer - not counted either way.\n"
                f"Current state: {state}{detail}\n\n"
                f"Question: {defect.question or '(none recorded)'}"
            )
            return

        if defect.status == "open":
            if present:
                logger.info(f"CONFIRMED  {header}{detail}")
                return
            raise AssertionError(
                f"{defect_id} is marked 'open' but the problem was NOT found.\n\n"
                f"{header}\n\n"
                f"Either it has been fixed, or this environment has no data that\n"
                f"triggers it. If it is genuinely fixed, set status: fixed in\n"
                f"resources/defects.yaml and re-run."
            )

        # status == "fixed"
        if present:
            raise AssertionError(
                f"REGRESSION - {defect_id} is marked 'fixed' but the problem is back.\n\n"
                f"{header}{detail}\n\n"
                f"{count} row(s) still affected. Re-open the defect."
            )
        logger.info(f"VERIFIED FIXED  {header}")

    @keyword("Check Defect")
    def check_defect(
        self, defect_id: str, rows: list[dict[str, Any]],
        finding: str = "", why: str = "",
    ) -> None:
        """Short alias for Findings Should Match Defect Register."""
        self.findings_should_match_defect_register(defect_id, rows, finding, why)

    @keyword("Defect Severity")
    def defect_severity(self, defect_id: str) -> str:
        return self._get(defect_id).severity

    @keyword("Defect Summary")
    def defect_summary(self, defect_id: str) -> str:
        return self._get(defect_id).summary

    @keyword("Log Defect Register")
    def log_defect_register(self) -> None:
        """Writes the whole register into the Robot log. Call in Suite Setup."""
        registry = self._registry()
        by_status: dict[str, list[str]] = {}
        for did, defect in sorted(registry.items()):
            by_status.setdefault(defect.status, []).append(
                f"  [{defect.severity}] {did}  {defect.summary[:88]}"
            )
        lines = [f"Defect register: {len(registry)} entries"]
        for status in ("open", "fixed", "ask"):
            entries = by_status.get(status, [])
            if entries:
                lines.append(f"\n{status.upper()} ({len(entries)}):")
                lines.extend(entries)
        logger.info("\n".join(lines))