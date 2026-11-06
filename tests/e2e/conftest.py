"""PDQA side E2E fixtures - writes expected_records.xlsx for the Facets suite."""
import os

import pytest

from e2e_excel import EXPECTED_FILE, SHARED_DIR
from expected_writer import ExpectedRecords

MARKERS = [
    "regression: regression suite",
    "practitioner_e2e: practitioner PDQA -> Facets handoff",
    "practice_e2e: practice PDQA -> Facets handoff",
    "facility_e2e: facility PDQA -> Facets handoff",
    "fallout: test that produces a fallout record",
]


# --------------------------------------------------------------------------- options
def pytest_addoption(parser):
    g = parser.getgroup("pdqa-e2e", "PDQA -> Facets handoff")
    g.addoption("--no-emit-expected", action="store_true",
                help="do not write expected_records.xlsx at the end of the run")
    g.addoption("--e2e-out", default=os.getenv("E2E_EXPECTED_FILE", ""),
                help="override the output path for expected_records.xlsx")
    g.addoption("--e2e-append", action="store_true",
                help="merge into the existing expected_records.xlsx instead of replacing it")
    g.addoption("--e2e-run-id", default=os.getenv("E2E_RUN_ID", ""),
                help="run id stamped on every row (defaults to a timestamp / CI build id)")
    g.addoption("--e2e-env", default=os.getenv("E2E_ENV", "SIT"),
                help="environment label stamped on every row")
    g.addoption("--e2e-publish", default=os.getenv("E2E_PUBLISH_DIR", ""),
                help="also copy the file to this shared folder after saving")
    g.addoption("--e2e-lenient", action="store_true",
                help="warn instead of failing when a recorded expectation is invalid")
    g.addoption("--e2e-allow-unknown-rules", action="store_true",
                help="warn instead of failing when a rule id is not yet in rules.py")


def pytest_configure(config):
    for m in MARKERS:
        config.addinivalue_line("markers", m)


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def expected_records(request):
    """Session-wide collector. Saved automatically at the end of the run."""
    rec = ExpectedRecords(
        run_id=request.config.getoption("--e2e-run-id"),
        env=request.config.getoption("--e2e-env"),
        strict=not request.config.getoption("--e2e-lenient"),
        allow_unknown_rules=request.config.getoption("--e2e-allow-unknown-rules"),
    )
    request.config._pdqa_expected = rec
    yield rec


@pytest.fixture
def record_fallout(expected_records, request):
    """Function-scoped helper - auto-stamps the test name onto each recorded row."""
    def _add(group, npi, rule_id=None, rule_ids=None, **kwargs):
        kwargs.setdefault("pdqa_test", request.node.name)
        if rule_ids:
            return expected_records.add_rules(group, npi, rule_ids, **kwargs)
        return expected_records.add(group, npi, rule_id or "", **kwargs)
    return _add


# --------------------------------------------------------------------------- teardown
def pytest_sessionfinish(session, exitstatus):
    rec = getattr(session.config, "_pdqa_expected", None)
    if rec is None or not rec.rows:
        return

    s = rec.summary()
    width = 100
    print("\n" + "=" * width)
    print(f" PDQA E2E HANDOFF   run_id={rec.run_id}   env={rec.env}   "
          f"{s['total']} expected record(s)")
    print("=" * width)
    for g, n in s["by_group"].items():
        print(f"  GROUP   {g:<16} {n}")
    print("-" * width)
    for r, n in s["by_rule"].items():
        print(f"  RULE    {r:<16} {n}")
    print("-" * width)
    for st, n in s["by_status"].items():
        print(f"  STATUS  {st:<16} {n}")
    if s["duplicates_skipped"]:
        print(f"  (deduplicated {s['duplicates_skipped']} repeated record(s))")
    print("=" * width)

    if session.config.getoption("--no-emit-expected"):
        print(" --no-emit-expected set: file NOT written\n")
        return

    out = session.config.getoption("--e2e-out") or EXPECTED_FILE
    try:
        path = rec.save(path=out,
                        append=session.config.getoption("--e2e-append"),
                        publish_dir=session.config.getoption("--e2e-publish") or None)
        print(f" Hand this file to the Facets suite: {path}")
        print(f" Facets side:  set E2E_SHARED_DIR={SHARED_DIR} && "
              f"set FACETS_REPORT=<report.xlsx> && pytest tests/e2e -v -s\n")
    except Exception as exc:
        print(f" [ERROR] could not write expected_records.xlsx: {exc}\n")
        raise
