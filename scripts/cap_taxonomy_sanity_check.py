#!/usr/bin/env python3
"""Sanity-check taxonomy metadata does not include redundant Brady/Jencks/Giglio flags."""

from __future__ import annotations

from taxonomy_embedding_agent import build_metadata


def main() -> int:
    taxonomy = {
        "ISS": [
            "FCD.ISS.DISCOVERY.BRADY",
            "FCD.ISS.DISCOVERY.JENCKS",
            "FCD.ISS.DISCOVERY.GIGLIO",
        ],
        "STG": ["FCD.STG.PRETRIAL"],
    }
    meta = build_metadata("cap_test", "cap", 0, taxonomy)

    forbidden = {"has_brady", "has_giglio", "has_jencks"}
    present = forbidden.intersection(meta.keys())
    if present:
        raise SystemExit(f"Unexpected derived flags present: {sorted(present)}")

    if "taxonomy" not in meta:
        raise SystemExit("Missing taxonomy in metadata")

    print("ok: taxonomy-only Brady/Jencks/Giglio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
