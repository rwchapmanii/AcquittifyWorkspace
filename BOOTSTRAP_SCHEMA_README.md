# Bootstrap Schema

Below is the **complete Acquittify Ontology Schema v1.0** — production-grade, file-based, idempotent, and graph-migration ready.

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

---

# 📁 ROOT STRUCTURE

```
/Casefile
    /00_Metadata
        case_config.json
        ontology_index.json
        entity_registry.json
        case_timeline.json
        bootstrap_log.json

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
  "trial_status": "",
  "bootstrap_version": "1.0",
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
  "bootstrap_version": "1.0"
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
  "bootstrap_version": "1.0"
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
  "appears_in": {
    "indictment": false,
    "counts": [],
    "transcripts": [],
    "exhibits": []
  },
  "testimony_text": "",
  "testimony_summary": "",
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
  "bootstrap_version": "1.0"
}
```

---

# 7️⃣ TRANSCRIPT NODE

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
  "bootstrap_version": "1.0"
}
```

---

# 8️⃣ EXHIBIT NODE

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
  "bootstrap_version": "1.0"
}
```

---

# 9️⃣ RELATIONSHIP GRAPH

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

---

# 🔟 TIMELINE

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

# 1️⃣1️⃣ BOOTSTRAP LOG

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
