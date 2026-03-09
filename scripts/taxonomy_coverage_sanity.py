#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify_taxonomy import TAXONOMY_SET
from admin_ui.taxonomy_utils import compute_coverage


def main() -> int:
    sample_codes = set(list(TAXONOMY_SET)[:5])
    if not sample_codes:
        print("No taxonomy codes available to test.")
        return 1
    result = compute_coverage(sample_codes, TAXONOMY_SET, "FCD-1.0", "local")
    print("Coverage sanity:", result)
    if result["covered_nodes"] != len(sample_codes):
        print("Coverage sanity failed: mismatch between sample and covered codes.")
        return 2
    print("Coverage sanity passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
