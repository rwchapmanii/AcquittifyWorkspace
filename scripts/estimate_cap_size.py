#!/usr/bin/env python3
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

SLUGS = set([
    "alaska-fed","ccpa","cma","ct-cust","ct-intl-trade","cust-ct","d-haw","ed-pa",
    "f","f-appx","f-cas","f-supp","f-supp-2d","f-supp-3d","f2d","f3d","fed-cl",
    "frd","n-mar-i-commw","pr-fed","us","us-app-dc","us-ct-cl","vet-app",
])

LIST_BASE = "https://storage.courtlistener.com/"


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def _list_prefix_sizes(prefix: str, rate: float = 1.0) -> tuple[int, int]:
    total_bytes = 0
    object_count = 0
    continuation = None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if continuation:
            params["continuation-token"] = continuation
        response = requests.get(LIST_BASE, params=params, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        for item in root.findall(".//{*}Contents"):
            size_text = item.findtext("{*}Size") or "0"
            try:
                size = int(size_text)
            except ValueError:
                size = 0
            total_bytes += size
            object_count += 1
        truncated = (root.findtext("{*}IsTruncated") or "").lower() == "true"
        continuation = root.findtext("{*}NextContinuationToken")
        if not truncated or not continuation:
            break
        time.sleep(rate)
    return total_bytes, object_count


def main() -> None:
    total = 0
    by_slug = {}
    counts = {}
    for slug in sorted(SLUGS):
        prefix = f"{slug}/"
        bytes_total, objects = _list_prefix_sizes(prefix)
        by_slug[slug] = bytes_total
        counts[slug] = objects
        total += bytes_total
        time.sleep(1.0)

    report = {
        "total_bytes": total,
        "total_human": human(total),
        "by_slug": by_slug,
        "object_counts": counts,
    }
    log_path = Path("acquittify-data/logs/size_estimate.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print("total_bytes", total)
    print("total_human", human(total))
    print("report", log_path)


if __name__ == "__main__":
    main()
