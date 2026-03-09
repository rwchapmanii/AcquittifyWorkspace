#!/usr/bin/env python3
"""Sanity-check case type classification without LLM."""

from __future__ import annotations

import os

from scripts.ingest_cap_jsonl import classify_case_type


def main() -> None:
    os.environ["ACQUITTIFY_CASE_CLASSIFY_MODE"] = "heuristic"

    criminal = classify_case_type(
        "United States v. Doe",
        ["18 U.S.C. § 1343"],
        "Defendant was indicted under 18 U.S.C. § 1343 for wire fraud.",
        2000,
        mode="heuristic",
    )
    quasi = classify_case_type(
        "In re Smith",
        [],
        "Petitioner seeks relief under 28 U.S.C. § 2255 after an administrative sanction.",
        2000,
        mode="heuristic",
    )
    non_criminal = classify_case_type(
        "Acme Corp v. Beta LLC",
        [],
        "This is a contract dispute concerning delivery terms and damages.",
        2000,
        mode="heuristic",
    )

    assert criminal["case_type"] == "criminal", criminal
    assert quasi["case_type"] == "quasi_criminal", quasi
    assert non_criminal["case_type"] == "non_criminal", non_criminal

    print("ok", {
        "criminal": criminal,
        "quasi": quasi,
        "non_criminal": non_criminal,
    })


if __name__ == "__main__":
    main()
