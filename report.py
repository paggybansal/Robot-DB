"""Report generation for the PDQA -> Facets reconciliation (HTML + Excel)."""
from __future__ import annotations

import getpass
import html
import platform
import socket
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Populated by conftest / fixtures during the run
RUN_INFO: dict = {}

RESULT_COLUMNS = ["GROUP", "SCENARIO", "SYMPLR ID", "TAXID", "NPI", "GNPI", "RULE ID",
                  "EXPECTED STATUS", "PDQA RUN TIME", "RESULT", "REMARKS", "FACETS ROW"]

_GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")
_RED_FILL   = PatternFill("solid", fgColor="FFC7CE")
_HEAD_FILL  = PatternFill("solid", fgColor="1F3864")
_THIN       = Side(style="thin", color="BFBFBF")
_BORDER     = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


# --------------------------------------------------------------------------- helpers
def classify(remark: str) -> str:
    r = (remark or "").upper()
    if "NOT FOUND" in r:
        return "Missing in Facets"
    if "STATUS MISMATCH" in r:
        return "Status mismatch"
    if "RULE ID" in r and "MISSING" in r:
        return "Rule not raised"
    if "DUPLICATE" in r:
        return "Duplicate rows"
    if "MISSING COLUMN" in r or "MISSING REQUIRED" in r:
        return "Report structure"
    if "FOUND IN FACETS REPORT" in r:
        return "Matched"
    return "Other"


def summarise(results: list) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["RESULT"] == "PASS")
    failed = total - passed

    by_group, by_reason = {}, {}
    for r in results:
        g = by_group.setdefault(r.get("GROUP", "?"), {"total": 0, "pass": 0, "fail": 0})
        g["total"] += 1
        g["pass" if r["RESULT"] == "PASS" else "fail"] += 1
        if r["RESULT"] == "FAIL":
            reason = classify(r.get("REMARKS", ""))
            by_reason[reason] = by_reason.get(reason, 0) + 1

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "by_group": by_group,
        "by_reason": dict(sorted(by_reason.items(), key=lambda kv: -kv[1])),
    }


def _duration() -> str:
    started = RUN_INFO.get("started_at")
    if not started:
        return "-"
    delta = datetime.now() - started
    secs = int(delta.total_seconds())
    return f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"


# --------------------------------------------------------------------------- EXCEL
def write_excel(results: list, out_path: Path) -> Path:
    s = summarise(results)
    wb = Workbook()

    # ---------------- Summary sheet ----------------
    ws = wb.active
    ws.title = "Summary"
    ws.append(["PDQA -> FACETS E2E RECONCILIATION"])
    ws["A1"].font = Font(size=14, bold=True, color="1F3864")
    ws.append([])
    for label, value in [
        ("Overall result",   "PASSED" if s["failed"] == 0 else "FAILED"),
        ("Total records",    s["total"]),
        ("Passed",           s["passed"]),
        ("Failed",           s["failed"]),
        ("Pass rate (%)",    s["pass_rate"]),
        ("Generated at",     datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Duration",         _duration()),
        ("Expected file",    str(RUN_INFO.get("expected_file", "-"))),
        ("Facets report",    str(RUN_INFO.get("report_file", "-"))),
        ("Executed by",      RUN_INFO.get("user", "-")),
        ("Machine",          RUN_INFO.get("host", "-")),
    ]:
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)

    ws.append([])
    ws.append(["GROUP", "TOTAL", "PASS", "FAIL"])
    for c in range(1, 5):
        cell = ws.cell(row=ws.max_row, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEAD_FILL
    for g, v in s["by_group"].items():
        ws.append([g, v["total"], v["pass"], v["fail"]])

    if s["by_reason"]:
        ws.append([])
        ws.append(["FAILURE CATEGORY", "COUNT"])
        for c in range(1, 3):
            cell = ws.cell(row=ws.max_row, column=c)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = _HEAD_FILL
        for reason, count in s["by_reason"].items():
            ws.append([reason, count])

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 70

    # ---------------- Source tabs sheet ----------------
    tabs = RUN_INFO.get("tabs", [])
    if tabs:
        wt = wb.create_sheet("Source Tabs")
        headers = ["GROUP", "SHEET", "EXECUTION AUDIT STATUS", "PROCESSED RECORD COUNT",
                   "ROWS PARSED", "HEADER ROW INDEX", "TITLE"]
        wt.append(headers)
        for c in range(1, len(headers) + 1):
            cell = wt.cell(row=1, column=c)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = _HEAD_FILL
        for t in tabs:
            wt.append([t.get("group"), t.get("sheet"), t.get("audit_status"),
                       t.get("processed_count"), t.get("rows_parsed"),
                       t.get("header_row_index"), t.get("title")])
        for i, w in enumerate([16, 20, 28, 24, 14, 18, 50], start=1):
            wt.column_dimensions[get_column_letter(i)].width = w
        wt.freeze_panes = "A2"

    # ---------------- Details sheet ----------------
    wd = wb.create_sheet("Details")
    wd.append(RESULT_COLUMNS)
    for c in range(1, len(RESULT_COLUMNS) + 1):
        cell = wd.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEAD_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    for r in results:
        wd.append([r.get(c, "") for c in RESULT_COLUMNS])
        row_idx = wd.max_row
        fill = _GREEN_FILL if r["RESULT"] == "PASS" else _RED_FILL
        font = Font(bold=True, color="006100" if r["RESULT"] == "PASS" else "9C0006")
        rcol = RESULT_COLUMNS.index("RESULT") + 1
        wd.cell(row=row_idx, column=rcol).fill = fill
        wd.cell(row=row_idx, column=rcol).font = font
        for c in range(1, len(RESULT_COLUMNS) + 1):
            wd.cell(row=row_idx, column=c).border = _BORDER
            wd.cell(row=row_idx, column=c).alignment = Alignment(vertical="top", wrap_text=True)

    widths = {"GROUP": 15, "SCENARIO": 26, "SYMPLR ID": 13, "TAXID": 13, "NPI": 13,
              "GNPI": 13, "RULE ID": 11, "EXPECTED STATUS": 16, "PDQA RUN TIME": 19,
              "RESULT": 9, "REMARKS": 55, "FACETS ROW": 90}
    for i, col in enumerate(RESULT_COLUMNS, start=1):
        wd.column_dimensions[get_column_letter(i)].width = widths.get(col, 18)
    wd.freeze_panes = "A2"
    wd.auto_filter.ref = f"A1:{get_column_letter(len(RESULT_COLUMNS))}{wd.max_row}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


# --------------------------------------------------------------------------- HTML
_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f4f6fa;color:#1f2430;
     font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:28px}
header{background:linear-gradient(135deg,#1f3864,#2e5aa8);color:#fff;border-radius:12px;
       padding:26px 30px;display:flex;justify-content:space-between;align-items:center;
       flex-wrap:wrap;gap:16px;box-shadow:0 6px 18px rgba(31,56,100,.22)}
header h1{margin:0;font-size:21px;letter-spacing:.3px}
header .sub{opacity:.85;font-size:13px;margin-top:5px}
.badge{font-size:17px;font-weight:700;padding:11px 26px;border-radius:30px;letter-spacing:1px}
.badge.ok{background:#1fa463;color:#fff}
.badge.ko{background:#d93636;color:#fff}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:16px;margin:22px 0}
.card{background:#fff;border-radius:11px;padding:18px 20px;box-shadow:0 2px 7px rgba(0,0,0,.07);
      border-left:5px solid #2e5aa8}
.card.ok{border-left-color:#1fa463}.card.ko{border-left-color:#d93636}
.card .k{font-size:11px;text-transform:uppercase;letter-spacing:.9px;color:#6b7280}
.card .v{font-size:28px;font-weight:700;margin-top:6px}
.bar{height:11px;border-radius:6px;background:#e4e7ee;overflow:hidden;margin-top:12px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#1fa463,#54c88c)}
section{background:#fff;border-radius:11px;padding:20px 22px;margin-bottom:20px;
        box-shadow:0 2px 7px rgba(0,0,0,.06)}
section h2{margin:0 0 14px;font-size:15px;color:#1f3864;
           border-bottom:2px solid #eef1f6;padding-bottom:9px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#1f3864;color:#fff;text-align:left;padding:10px 11px;font-weight:600;
   position:sticky;top:0;z-index:2;font-size:12px}
td{padding:9px 11px;border-bottom:1px solid #eceff4;vertical-align:top}
tr.pass td:first-child{border-left:4px solid #1fa463}
tr.fail td:first-child{border-left:4px solid #d93636}
tr.fail{background:#fff6f6}
tr:hover{background:#f0f4fb}
.pill{display:inline-block;padding:3px 11px;border-radius:12px;font-size:11px;font-weight:700}
.pill.pass{background:#d7f2e3;color:#116b43}
.pill.fail{background:#fbd9d9;color:#9c1c1c}
.mono{font-family:Consolas,Menlo,monospace;font-size:11.5px;color:#444;word-break:break-word}
.kv{display:grid;grid-template-columns:190px 1fr;gap:7px 16px;font-size:13px}
.kv b{color:#55607a;font-weight:600}
.controls{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:13px}
.controls input{flex:1;min-width:230px;padding:9px 13px;border:1px solid #d3d9e3;
                border-radius:7px;font-size:13px}
.btn{padding:8px 15px;border:1px solid #d3d9e3;background:#fff;border-radius:7px;
     cursor:pointer;font-size:12.5px;font-weight:600;color:#44506b}
.btn.active{background:#1f3864;color:#fff;border-color:#1f3864}
.scroll{max-height:640px;overflow:auto;border:1px solid #eceff4;border-radius:8px}
footer{text-align:center;color:#8a93a6;font-size:12px;padding:16px 0 26px}
@media print{.controls,.btn{display:none}.scroll{max-height:none}}
"""

_JS = """
function applyFilter(){
  var q=document.getElementById('q').value.toLowerCase();
  var f=document.querySelector('.btn.active').dataset.f;
  var shown=0;
  document.querySelectorAll('#tbl tbody tr').forEach(function(tr){
    var okF=(f==='all')||tr.classList.contains(f);
    var okQ=!q||tr.innerText.toLowerCase().indexOf(q)>-1;
    tr.style.display=(okF&&okQ)?'':'none';
    if(okF&&okQ)shown++;
  });
  document.getElementById('count').innerText=shown+' row(s)';
}
document.querySelectorAll('.btn[data-f]').forEach(function(b){
  b.onclick=function(){
    document.querySelectorAll('.btn[data-f]').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');applyFilter();};
});
document.getElementById('q').addEventListener('input',applyFilter);
applyFilter();
"""


def _e(v) -> str:
    return html.escape(str(v if v is not None else ""))


def write_html(results: list, out_path: Path) -> Path:
    s = summarise(results)
    ok = s["failed"] == 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cards = f"""
    <div class="cards">
      <div class="card"><div class="k">Total records</div><div class="v">{s['total']}</div></div>
      <div class="card ok"><div class="k">Passed</div><div class="v">{s['passed']}</div></div>
      <div class="card ko"><div class="k">Failed</div><div class="v">{s['failed']}</div></div>
      <div class="card"><div class="k">Pass rate</div><div class="v">{s['pass_rate']}%</div>
        <div class="bar"><i style="width:{s['pass_rate']}%"></i></div></div>
      <div class="card"><div class="k">Duration</div><div class="v">{_duration()}</div></div>
    </div>"""

    run_info = f"""
    <section><h2>Run information</h2><div class="kv">
      <b>Generated at</b><span>{_e(now)}</span>
      <b>PDQA expectation file</b><span class="mono">{_e(RUN_INFO.get('expected_file','-'))}</span>
      <b>Facets report file</b><span class="mono">{_e(RUN_INFO.get('report_file','-'))}</span>
      <b>Executed by</b><span>{_e(RUN_INFO.get('user','-'))} @ {_e(RUN_INFO.get('host','-'))}</span>
      <b>Platform</b><span>{_e(RUN_INFO.get('platform','-'))}</span>
      <b>Match keys</b><span>NPI + GNPI + TAXID + RULE ID</span>
    </div></section>"""

    grp_rows = "".join(
        f"<tr><td><b>{_e(g)}</b></td><td>{v['total']}</td>"
        f"<td style='color:#116b43;font-weight:600'>{v['pass']}</td>"
        f"<td style='color:#9c1c1c;font-weight:600'>{v['fail']}</td>"
        f"<td>{round(v['pass'] / v['total'] * 100, 1) if v['total'] else 0}%</td></tr>"
        for g, v in s["by_group"].items())
    grp = f"""
    <section><h2>Breakdown by group</h2><table>
      <thead><tr><th>Group</th><th>Total</th><th>Passed</th><th>Failed</th><th>Pass rate</th></tr></thead>
      <tbody>{grp_rows}</tbody></table></section>"""

    tabs = RUN_INFO.get("tabs", [])
    tab_html = ""
    if tabs:
        rows = "".join(
            f"<tr><td><b>{_e(t.get('group'))}</b></td><td>{_e(t.get('sheet'))}</td>"
            f"<td>{_e(t.get('audit_status'))}</td><td>{_e(t.get('processed_count'))}</td>"
            f"<td>{_e(t.get('rows_parsed'))}</td><td>{_e(t.get('header_row_index'))}</td></tr>"
            for t in tabs)
        tab_html = f"""
        <section><h2>Facets report tabs consumed</h2><table>
          <thead><tr><th>Group</th><th>Sheet</th><th>Execution audit status</th>
          <th>Processed record count</th><th>Rows parsed</th><th>Header row</th></tr></thead>
          <tbody>{rows}</tbody></table></section>"""

    reason_html = ""
    if s["by_reason"]:
        rows = "".join(f"<tr><td>{_e(k)}</td><td><b>{v}</b></td></tr>"
                       for k, v in s["by_reason"].items())
        reason_html = f"""
        <section><h2>Failure categories</h2><table>
          <thead><tr><th>Category</th><th>Count</th></tr></thead>
          <tbody>{rows}</tbody></table></section>"""

    det_rows = []
    for r in results:
        cls = "pass" if r["RESULT"] == "PASS" else "fail"
        det_rows.append(
            f"<tr class='{cls}'>"
            f"<td><span class='pill {cls}'>{_e(r['RESULT'])}</span></td>"
            f"<td>{_e(r.get('GROUP'))}</td>"
            f"<td>{_e(r.get('RULE ID'))}</td>"
            f"<td class='mono'>{_e(r.get('NPI'))}</td>"
            f"<td class='mono'>{_e(r.get('GNPI'))}</td>"
            f"<td class='mono'>{_e(r.get('TAXID'))}</td>"
            f"<td class='mono'>{_e(r.get('SYMPLR ID'))}</td>"
            f"<td>{_e(r.get('EXPECTED STATUS'))}</td>"
            f"<td>{_e(r.get('SCENARIO'))}</td>"
            f"<td>{_e(r.get('REMARKS'))}</td>"
            f"<td class='mono'>{_e(r.get('FACETS ROW'))}</td></tr>")

    details = f"""
    <section><h2>Record level results</h2>
      <div class="controls">
        <button class="btn active" data-f="all">All</button>
        <button class="btn" data-f="pass">Passed</button>
        <button class="btn" data-f="fail">Failed</button>
        <input id="q" placeholder="Search NPI, GNPI, TaxID, rule, scenario, remark...">
        <span id="count" style="color:#6b7280;font-size:12px"></span>
      </div>
      <div class="scroll"><table id="tbl">
        <thead><tr><th>Result</th><th>Group</th><th>Rule</th><th>NPI</th><th>GNPI</th>
        <th>TaxID</th><th>Symplr ID</th><th>Exp. status</th><th>Scenario</th>
        <th>Remarks</th><th>Facets row</th></tr></thead>
        <tbody>{''.join(det_rows)}</tbody>
      </table></div>
    </section>"""

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>PDQA &rarr; Facets E2E Reconciliation Report</title><style>{_CSS}</style></head><body>
<div class="wrap">
  <header>
    <div><h1>PDQA &rarr; Facets E2E Reconciliation</h1>
      <div class="sub">Fallout records verified in the Facets pipeline audit log after the sync job</div></div>
    <div class="badge {'ok' if ok else 'ko'}">{'PASSED' if ok else 'FAILED'}</div>
  </header>
  {cards}{run_info}{grp}{tab_html}{reason_html}{details}
  <footer>Generated {_e(now)} &middot; tests/e2e/test_pdqa_to_facets.py</footer>
</div>
<script>{_JS}</script></body></html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def init_run_info(expected_file, report_file):
    RUN_INFO.update({
        "started_at": datetime.now(),
        "expected_file": str(expected_file),
        "report_file": str(report_file),
        "user": _safe(getpass.getuser),
        "host": _safe(socket.gethostname),
        "platform": f"{platform.system()} {platform.release()} / Python {platform.python_version()}",
        "tabs": [],
    })


def _safe(fn):
    try:
        return fn()
    except Exception:
        return "-"
