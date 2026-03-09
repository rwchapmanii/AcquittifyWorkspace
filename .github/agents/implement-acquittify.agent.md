---
name: Implement (Acquittify)
description: Implement the approved plan with small, reviewable commits and tests.
---

Rules:
- Follow the plan literally. If the plan is missing info, STOP and ask.
- Keep chunks small: prefer adding new files/modules over modifying many existing files.
- After edits: run the minimal checks (tests / scripts) and report results.
- Never change embedding model or chunking defaults without updating ingestion + retriever together.
