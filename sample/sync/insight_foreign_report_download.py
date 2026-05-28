from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    items = gangtise.insight.foreign_report_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for insight.foreign_report_download.")
    row = items.iloc[0]
    item_id = row.get("reportId") or row.get("id")
    if not item_id:
        raise SystemExit("Could not find an ID column in the list response.")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.insight.foreign_report_download(
            report_id=item_id,
            file_type=1,
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    main()
