# Bootstrap Schema

Below is the **complete Acquittify Ontology Schema v1.2** — production-grade, file-based, idempotent, and graph-migration ready.

This is the full JSON schema architecture for every node type, metadata structure, and relationship model.

It is designed to:

* Be deterministic
* Be merge-safe
* Support Rule 29 analysis
* Support impeachment modeling
* Support sentencing exposure modeling
* Support future Neo4j migration
* Never require schema refactor later

---

# 🔷 GLOBAL DESIGN PRINCIPLES

1. Every node has:

   * `node_id`
   * `node_type`
   * `canonical_name`
   * `created_at`
   * `last_updated`
   * `source_files`
   * `bootstrap_version`

2. No destructive overwrites.

3. All relationships are recorded in `/06_Link_Graph/relationships.json`.

4. All entities are canonicalized in `/00_Metadata/entity_registry.json`.

5. Every bootstrap JSON file must have a same-name markdown sidecar in the same folder
   (for example, `count_1.json` and `count_1.md`) that carries the established bootstrap schema context.

---

# 🧭 WITNESS NAME EXTRACTION CONTRACT (REQUIRED)

Witness node creation must follow this ordered source hierarchy:

1. **Transcript-first (primary source)**  
   Extract witness names only when the transcript expressly identifies who is testifying, such as:
   - `THE WITNESS: <Name>`
   - `A. My name is <Name>` / `A. I am <Name>`
   - `DIRECT EXAMINATION OF <Name>` / `CROSS-EXAMINATION OF <Name>`
   - `Testimony of <Name>`

2. **Fallback sources (only when transcript witness identification is absent)**  
   Use names from:
   - Government witness lists
   - Defense witness lists
   - Law-enforcement interview/statement documents (interviewee names)

3. **Prohibited extraction behavior**
   - Do not create witness nodes from generic transcript prose.
   - Do not create witness nodes from arbitrary Q/A fragments.
   - Do not create witness nodes from short phrase matches that are not express witness identifiers.

4. **Determinism and de-duplication**
   - Canonicalize person names before node creation.
   - Merge aliases under one witness node.
   - Reject non-person phrases even if they superficially match title case.

5. **Document-linking witness synthesis (required)**
   - After witness identities are established, scan every extracted case document for those witness names.
   - For each matching document, add a witness appearance-chart row with document link/path, role in that document, involvement summary, excerpt, linked counts, and confidence.
   - Populate witness-level overall summary + testimony/potential-testimony summaries from these chart rows.

---

# 📁 ROOT STRUCTURE

Every `.json` bootstrap artifact below is expected to have a same-name `.md` sidecar in the same directory.

```
/Casefile
    /00_Metadata
        case_config.json
        ontology_index.json
        entity_registry.json
        case_timeline.json
        bootstrap_log.json
        bootstrap_source_index.json
        bootstrap_refresh_report.json

    /01_Charging_Documents
        indictment_primary.json
        indictment_superseding.json

    /02_Counts
        count_<number>.json

    /03_Witnesses
        witness_<canonical_name>.json

    /04_Transcripts
        transcript_<id>.json

    /05_Exhibits
        exhibit_<id>.json

    /06_Link_Graph
        relationships.json

    /07_Attorneys
        attorney_<canonical_name>.json
```

---

# 1️⃣ CASE CONFIG

### `/00_Metadata/case_config.json`

```json
{
  "case_id": "",
  "jurisdiction": "",
  "court": "",
  "judge": "",
  "defendants": [],
  "lead_defense_counsel": "",
  "defense_counsel": [],
  "prosecution_counsel": [],
  "trial_status": "",
  "bootstrap_version": "1.2",
  "created_at": "",
  "last_updated": ""
}
```

---

# 2️⃣ ONTOLOGY INDEX

Tracks all nodes.

### `/00_Metadata/ontology_index.json`

```json
{
  "indictments": [],
  "counts": [],
  "witnesses": [],
  "attorneys": [],
  "transcripts": [],
  "exhibits": [],
  "entities": [],
  "relationships_total": 0,
  "last_updated": ""
}
```

---

# 3️⃣ ENTITY REGISTRY (CANONICALIZATION CORE)

### `/00_Metadata/entity_registry.json`

```json
{
  "persons": {
    "John_Doe": {
      "canonical_name": "John Doe",
      "aliases": ["Johnny Doe", "J. Doe"],
      "entity_type": "person",
      "linked_nodes": [],
      "created_at": "",
      "last_updated": ""
    }
  },
  "attorneys": {
    "Andrew_E_Smith": {
      "canonical_name": "Andrew E Smith",
      "aliases": [],
      "side": "prosecution",
      "represents": ["United States"],
      "linked_nodes": [],
      "created_at": "",
      "last_updated": ""
    }
  },
  "organizations": {},
  "corporations": {},
  "government_agents": {},
  "statutes": {
    "18_USC_1343": {
      "canonical_name": "18 U.S.C. § 1343",
      "title": "Wire Fraud",
      "elements": [],
      "linked_counts": []
    }
  }
}
```

---

# 4️⃣ INDICTMENT NODE

### `/01_Charging_Documents/indictment_primary.json`

```json
{
  "node_id": "indictment_primary",
  "node_type": "Indictment",
  "canonical_name": "Primary Indictment",
  "superseding": false,
  "version_number": 1,
  "file_path": "",
  "full_text": "",
  "counts_detected": [],
  "defendants": [],
  "statutes_cited": [],
  "named_persons": [],
  "named_entities": [],
  "overt_acts": [],
  "date_filed": "",
  "created_at": "",
  "last_updated": "",
  "source_files": [],
  "bootstrap_version": "1.2"
}
```

If superseding:

```json
"superseding": true,
"overrides": "indictment_primary"
```

---

# 5️⃣ COUNT NODE

### `/02_Counts/count_<number>.json`

```json
{
  "node_id": "count_1",
  "node_type": "Count",
  "canonical_name": "Count 1",
  "count_number": 1,
  "statutes": [],
  "statutory_elements": [],
  "full_text": "",
  "defendant_conduct_alleged": "",
  "mens_rea_alleged": "",
  "financial_exposure": null,
  "forfeiture_alleged": null,
  "date_range": "",
  "locations": [],
  "named_witnesses": [],
  "linked_exhibits": [],
  "linked_transcripts": [],
  "elements_status": {
    "element_1": {
      "text": "",
      "supporting_witnesses": [],
      "supporting_exhibits": [],
      "defense_gaps": [],
      "confidence_score": 0.0
    }
  },
  "rule_29_vulnerability_score": null,
  "created_at": "",
  "last_updated": "",
  "source_files": [],
  "bootstrap_version": "1.2"
}
```

---

# 6️⃣ WITNESS NODE

### `/03_Witnesses/witness_<canonical_name>.json`

```json
{
  "node_id": "witness_john_doe",
  "node_type": "Witness",
  "canonical_name": "John Doe",
  "aliases": [],
  "role": null,
  "overall_summary": "",
  "appears_in": {
    "indictment": false,
    "counts": [],
    "transcripts": [],
    "exhibits": [],
    "statements": [],
    "affidavits": [],
    "documents": []
  },
  "testimony_text": "",
  "testimony_summary": "",
  "potential_testimony_summary": "",
  "document_appearance_chart": [
    {
      "document_path": "",
      "document_name": "",
      "document_type": "transcript | statement | affidavit | witness_list | exhibit | indictment | document",
      "source_node_id": "",
      "role_in_document": "",
      "involvement_summary": "",
      "excerpt": "",
      "linked_counts": [],
      "link": "",
      "confidence": 0.0
    }
  ],
  "linked_documents": [
    {
      "document_path": "",
      "document_type": "",
      "source_node_id": "",
      "role_in_document": "",
      "involvement_summary": "",
      "linked_counts": [],
      "link": ""
    }
  ],
  "statements": [],
  "linked_witnesses": [],
  "linked_entities": [],
  "internal_inconsistencies": [],
  "cross_witness_conflicts": [],
  "credibility_flags": [],
  "impeachment_material": [],
  "timeline_events": [],
  "strategic_value_score": null,
  "impeachment_value_score": null,
  "credibility_risk_score": null,
  "created_at": "",
  "last_updated": "",
  "source_files": [],
  "bootstrap_version": "1.2"
}
```

---

# 7️⃣ ATTORNEY NODE

### `/07_Attorneys/attorney_<canonical_name>.json`

```json
{
  "node_id": "attorney_andrew_e_smith",
  "node_type": "Attorney",
  "canonical_name": "Andrew E Smith",
  "aliases": [],
  "side": "prosecution | defense | null",
  "represents": ["United States"],
  "appears_in": {
    "counts": [],
    "transcripts": []
  },
  "statements": [],
  "created_at": "",
  "last_updated": "",
  "source_files": [],
  "bootstrap_version": "1.2"
}
```

---

# 8️⃣ TRANSCRIPT NODE

### `/04_Transcripts/transcript_<id>.json`

```json
{
  "node_id": "transcript_20240212_trial_day_3",
  "node_type": "Transcript",
  "canonical_name": "Trial Day 3 - Feb 12 2024",
  "date": "",
  "proceeding_type": "",
  "witness_on_stand": "",
  "direct_exam": [],
  "cross_exam": [],
  "redirect_exam": [],
  "recross_exam": [],
  "linked_counts": [],
  "linked_exhibits": [],
  "referenced_persons": [],
  "referenced_entities": [],
  "created_at": "",
  "last_updated": "",
  "source_files": [],
  "bootstrap_version": "1.2"
}
```

---

# 9️⃣ EXHIBIT NODE

### `/05_Exhibits/exhibit_<id>.json`

```json
{
  "node_id": "exhibit_gov_12",
  "node_type": "Exhibit",
  "canonical_name": "Government Exhibit 12",
  "exhibit_id": "",
  "type": "",
  "date": "",
  "authors": [],
  "recipients": [],
  "mentioned_entities": [],
  "linked_witnesses": [],
  "linked_counts": [],
  "summary": "",
  "full_text": "",
  "bates_range": "",
  "file_path": "",
  "relevance_score": null,
  "created_at": "",
  "last_updated": "",
  "source_files": [],
  "bootstrap_version": "1.2"
}
```

---

# 🔟 RELATIONSHIP GRAPH

### `/06_Link_Graph/relationships.json`

```json
[
  {
    "relationship_id": "",
    "source_node": "",
    "target_node": "",
    "relationship_type": "",
    "context_excerpt": "",
    "confidence": 0.0,
    "created_at": ""
  }
]
```

Allowed relationship types:

* charged_in
* testifies_about
* authored
* received
* mentioned
* relates_to_count
* relates_to_statute
* co_conspirator_with
* contradicted_by
* impeached_by
* supports_element
* fails_to_support_element
* references
* part_of_scheme
* represented_by

---

# 1️⃣1️⃣ TIMELINE

### `/00_Metadata/case_timeline.json`

```json
[
  {
    "event_id": "",
    "date": "",
    "date_precision": "exact | approximate | range",
    "description": "",
    "related_nodes": [],
    "confidence": 0.0
  }
]
```

---

# 1️⃣2️⃣ BOOTSTRAP LOG

### `/00_Metadata/bootstrap_log.json`

```json
[
  {
    "timestamp": "",
    "action": "",
    "node_affected": "",
    "details": "",
    "confidence": 0.0
  }
]
```

---

# 1️⃣3️⃣ BOOTSTRAP SOURCE INDEX

### `/00_Metadata/bootstrap_source_index.json`

```json
{
  "version": 1,
  "generated_at": "",
  "mode": "deep",
  "operation": "bootstrap | refresh",
  "documents": [
    {
      "path": "",
      "file_name": "",
      "doc_type": "",
      "text_hash": "",
      "size_bytes": 0,
      "mtime_ms": 0,
      "scanned_chars": 0,
      "scanned_at": ""
    }
  ]
}
```

---

# 1️⃣4️⃣ BOOTSTRAP REFRESH REPORT

### `/00_Metadata/bootstrap_refresh_report.json`

```json
{
  "timestamp": "",
  "operation": "bootstrap | refresh",
  "mode": "deep",
  "summary": {
    "requested": false,
    "new_documents": 0,
    "updated_documents": 0,
    "removed_documents": 0,
    "analyzed_documents": 0
  },
  "new_documents": [],
  "updated_documents": [],
  "removed_documents": [],
  "analyzed_documents": [
    {
      "path": "",
      "file_name": "",
      "document_type": "",
      "count_refs": [],
      "explicit_witness_names": [],
      "witness_list_names": [],
      "interviewee_names": [],
      "attorney_names": [],
      "impact_summary": ""
    }
  ]
}
```
