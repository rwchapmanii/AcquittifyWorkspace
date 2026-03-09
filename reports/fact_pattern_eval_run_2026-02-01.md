# Fact Pattern Evaluation — 2026-02-01

## What I did
- Replaced eval/fact_patterns.jsonl with 50 federal criminal defense fact patterns.
- Ran the fact-pattern evaluation script against the current corpus and LLM.
- Improved evaluation reliability by adding a fallback call when the model returns an empty response.

## Results
- Total patterns: 50
- LLM available: True
- Average sources retrieved: 5.0
- Headings OK: 50/50
- Authority Ladder OK: 50/50
- Follow-up questions OK: 50/50
- Citations expected: 50
- Citations present: 50

Source report: eval/fact_pattern_report.md

## Changes applied
- scripts/fact_pattern_eval.py: added a fallback LLM call when a response is empty.
- eval/fact_patterns.jsonl: replaced with 50 new fact patterns.

## Sanity check / test run
- .venv/bin/python scripts/fact_pattern_eval.py

## Suggested commit message (includes “what changed”)
- what changed: refresh fact patterns and improve eval retries to avoid empty responses.
