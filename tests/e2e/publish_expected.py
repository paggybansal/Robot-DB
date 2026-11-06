"""CI step: copy the generated expected_records.xlsx to the shared handoff location.

    python tests/e2e/publish_expected.py --dest //fileshare/e2e/pdqa-facets --run-id %BUILD_NUMBER%
"""
import argparse
import shutil
import sys
from pathlib import Path

from e2e_excel import EXPECTED_FILE, load_expected_records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(EXPECTED_FILE))
    ap.add_argument("--dest", required=True, help="shared folder / mounted drive")
    ap.add_argument("--run-id", default="", help="if set, also drop a run-stamped copy")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"[publish] nothing to publish - {src} does not exist")
        return 0

    rows = load_expected_records(src)
    if not rows:
        print(f"[publish] {src} has no data rows - aborting")
        return 1

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest / src.name)
    print(f"[publish] {len(rows)} record(s) -> {dest / src.name}")

    if args.run_id:
        stamped = dest / f"{src.stem}_{args.run_id}{src.suffix}"
        shutil.copy2(src, stamped)
        print(f"[publish] archived -> {stamped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
