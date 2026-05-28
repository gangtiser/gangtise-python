from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

_GTABLE_RE = re.compile(r"<gtable>(.*?)</gtable>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def show_result(result: Any, source_file: str) -> None:
    if hasattr(result, "to_string") and hasattr(result, "empty"):
        print(result.to_string(index=False))
        return
    if isinstance(result, Path):
        print(result)
        return

    source = Path(source_file)
    output_dir = source.parents[2] / "sample_outputs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"{source.parent.name}_{source.stem}.md"
    output_path.write_text(_to_markdown(result), encoding="utf-8")
    print(output_path)


def _to_markdown(value: Any) -> str:
    text = _render_value(value).strip()
    return text + "\n" if text else ""


def _render_value(value: Any) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        content = _first_text(
            value, ("content", "markdown", "summary", "logic", "outline", "discussion")
        )
        if content:
            prefix = _metadata_lines(value)
            body = _clean_text(content)
            return "\n".join([*prefix, body]).strip()
        return _render_mapping(value)
    if isinstance(value, list):
        if value and all(isinstance(row, dict) for row in value):
            return _dict_table(value)
        return "\n".join(_clean_text(str(item)) for item in value)
    return _clean_text(str(value))


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _metadata_lines(data: dict[str, Any]) -> list[str]:
    lines = []
    for key in ("status", "data_id", "dataId", "date", "message"):
        value = data.get(key)
        if value not in (None, ""):
            lines.append(f"{key}: {value}")
    return lines


def _render_mapping(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            rendered = _render_value(value)
            if rendered:
                lines.extend([f"## {key}", rendered, ""])
        elif value not in (None, ""):
            lines.append(f"{key}: {_clean_text(str(value))}")
    return "\n".join(lines).strip()


def _dict_table(rows: list[Any]) -> str:
    dict_rows = [row for row in rows if isinstance(row, dict)]
    columns = list(dict_rows[0].keys()) if dict_rows else []
    if not columns:
        return ""
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in dict_rows:
        lines.append("| " + " | ".join(_clean_cell(row.get(col)) for col in columns) + " |")
    return "\n".join(lines)


def _clean_cell(value: Any) -> str:
    return _clean_text("" if value is None else str(value)).replace("\n", " ")


def _clean_text(text: str) -> str:
    text = html.unescape(text)
    text = _GTABLE_RE.sub(lambda match: _gtable_to_markdown(match.group(1)), text)
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _TAG_RE.sub("", text)
    lines = [line.rstrip() for line in text.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    return "\n".join(compact).strip()


def _gtable_to_markdown(raw: str) -> str:
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(rows, list) or not rows or not all(isinstance(row, list) for row in rows):
        return raw
    header = [str(cell) for cell in rows[0]]
    body = rows[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n" + "\n".join(lines) + "\n"
