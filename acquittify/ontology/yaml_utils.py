from __future__ import annotations

from typing import Any


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def dump_yaml(data: Any, indent: int = 0) -> str:
    space = " " * indent

    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            key_str = str(key)
            if isinstance(value, (dict, list)):
                if not value:
                    empty = "{}" if isinstance(value, dict) else "[]"
                    lines.append(f"{space}{key_str}: {empty}")
                else:
                    lines.append(f"{space}{key_str}:")
                    lines.append(dump_yaml(value, indent + 2))
            else:
                lines.append(f"{space}{key_str}: {_scalar(value)}")
        return "\n".join(lines)

    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                if isinstance(item, dict) and not item:
                    lines.append(f"{space}- {{}}")
                elif isinstance(item, list) and not item:
                    lines.append(f"{space}- []")
                else:
                    lines.append(f"{space}-")
                    lines.append(dump_yaml(item, indent + 2))
            else:
                lines.append(f"{space}- {_scalar(item)}")
        return "\n".join(lines)

    return f"{space}{_scalar(data)}"


def markdown_with_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    frontmatter_block = dump_yaml(frontmatter)
    body_text = body if body.endswith("\n") else f"{body}\n"
    return f"---\n{frontmatter_block}\n---\n\n{body_text}"
