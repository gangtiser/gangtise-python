from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import DownloadError, gangtise


def main():
    items = gangtise.insight.research_list(size=10)
    if items.empty:
        raise SystemExit("No source item found for insight.research_download.")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    last_error = None
    for _, row in items.iterrows():
        item_id = row.get("reportId") or row.get("id")
        if not item_id:
            continue
        try:
            os.chdir(output_dir)
            result = gangtise.insight.research_download(
                report_id=item_id,
                file_type=1,
            )
        except DownloadError as exc:
            last_error = exc
            continue
        finally:
            os.chdir(previous_cwd)
        show_result(result, __file__)
        return
    raise SystemExit(f"No downloadable research report found. Last error: {last_error}")


if __name__ == "__main__":
    main()
