from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    items = await gangtise.async_.vault.record_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for vault.record_download.")
    row = items.iloc[0]
    item_id = row.get("recordId") or row.get("id") or row.get("id")
    if not item_id:
        raise SystemExit("Could not find an ID column in the list response.")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = await gangtise.async_.vault.record_download(
            record_id=item_id,
            content_type="original",
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
