from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    source_id = os.environ.get("GANGTISE_SAMPLE_KNOWLEDGE_SOURCE_ID")
    resource_type = os.environ.get("GANGTISE_SAMPLE_KNOWLEDGE_RESOURCE_TYPE", "1")
    if not source_id:
        raise SystemExit("Set GANGTISE_SAMPLE_KNOWLEDGE_SOURCE_ID to a downloadable sourceId.")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.ai.knowledge_resource_download(
            resource_type=int(resource_type),
            source_id=source_id,
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    main()
