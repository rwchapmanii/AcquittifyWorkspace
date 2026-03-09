import argparse
import json
from collections import Counter
from pathlib import Path


def _load_logs(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit empty retrievals for coverage gaps.")
    parser.add_argument("--log", default="Casefiles/retrieval_empty.jsonl", help="Empty retrieval log path")
    parser.add_argument("--report", default="eval/coverage_audit.json", help="Output report path")
    parser.add_argument("--top", type=int, default=25, help="Top items to include")
    args = parser.parse_args()

    rows = _load_logs(Path(args.log))
    if not rows:
        raise SystemExit("No empty retrieval logs found.")

    by_area = Counter()
    by_query = Counter()
    for row in rows:
        by_area[row.get("legal_area", "UNKNOWN")] += 1
        by_query[(row.get("query") or "").strip()] += 1

    report = {
        "total_empty": len(rows),
        "top_legal_areas": by_area.most_common(args.top),
        "top_queries": by_query.most_common(args.top),
    }

    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
