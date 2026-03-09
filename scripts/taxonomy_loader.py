#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

def _strip_quotes(value: str) -> str:
    if value.startswith("\"") and value.endswith("\""):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def _parse_inline_list(value: str) -> list[str] | None:
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            return None
    return None


def load_taxonomy(path: Path) -> dict:
    version = None
    nodes = []
    current = None

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("version:"):
            value = _strip_quotes(line.split(":", 1)[1].strip())
            version = value
            continue

        if line == "nodes:" or line.startswith("nodes:"):
            continue

        if line.startswith("-"):
            if current:
                nodes.append(current)
            current = {}
            line = line[1:].strip()
            if line:
                key, value = line.split(":", 1)
                current[key.strip()] = _strip_quotes(value.strip())
            continue

        if ":" in line and current is not None:
            key, value = line.split(":", 1)
            value = value.strip()
            if value.lower() == "null" or value == "":
                current[key.strip()] = None
            else:
                parsed_list = _parse_inline_list(value)
                if parsed_list is not None:
                    current[key.strip()] = parsed_list
                else:
                    current[key.strip()] = _strip_quotes(value)

    if current:
        nodes.append(current)

    if not version or not nodes:
        raise SystemExit("Taxonomy must include version and nodes")

    return {"version": version, "nodes": nodes}


def generate_sql(taxonomy: dict) -> str:
    version = taxonomy.get("version")
    nodes = taxonomy.get("nodes", [])

    if not version or not isinstance(nodes, list):
        raise SystemExit("Taxonomy must include 'version' and 'nodes' list")

    values = []
    codes = {node.get("code") for node in nodes if node.get("code")}
    for node in nodes:
        code = node.get("code")
        label = node.get("label")
        synonyms = node.get("synonyms") or []
        parent_code = ".".join(code.split("." )[:-1]) if code and "." in code else None
        if not code or not label:
            raise SystemExit("Each node must include 'code' and 'label'")
        parent_sql = "NULL" if parent_code is None else f"'{parent_code.replace("'", "''")}'"
        synonyms_json = json.dumps(list(synonyms)) if isinstance(synonyms, list) else json.dumps([])
        parent_sql = parent_sql if parent_code in codes else parent_sql
        values.append(
            "("
            f"'{code.replace("'", "''")}', "
            f"'{label.replace("'", "''")}', "
            f"{parent_sql}, "
            f"'{version.replace("'", "''")}', "
            f"'{synonyms_json.replace("'", "''")}'::jsonb"
            ")"
        )

    values_sql = ",\n    ".join(values)

    return (
        "BEGIN;\n"
        "ALTER TABLE IF EXISTS derived.taxonomy_node "
        "ADD COLUMN IF NOT EXISTS synonyms JSONB NOT NULL DEFAULT '[]'::jsonb;\n"
        "INSERT INTO derived.taxonomy_node (code, label, parent_code, version, synonyms) VALUES\n"
        f"    {values_sql}\n"
        "ON CONFLICT (code, version) DO UPDATE\n"
        "SET label = EXCLUDED.label,\n"
        "    parent_code = EXCLUDED.parent_code,\n"
        "    synonyms = EXCLUDED.synonyms,\n"
        "    updated_at = NOW();\n"
        "COMMIT;\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SQL for taxonomy upserts")
    parser.add_argument(
        "--file",
        default="taxonomy/2026.01/taxonomy.yaml",
        help="Path to taxonomy YAML (JSON-compatible)",
    )
    args = parser.parse_args()

    taxonomy = load_taxonomy(Path(args.file))
    sql = generate_sql(taxonomy)
    sys.stdout.write(sql)


if __name__ == "__main__":
    main()
