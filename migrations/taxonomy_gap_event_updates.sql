ALTER TABLE derived.taxonomy_gap_event
    ADD COLUMN IF NOT EXISTS suggested_parent_code TEXT;

CREATE INDEX IF NOT EXISTS taxonomy_gap_event_suggested_parent_idx
    ON derived.taxonomy_gap_event (suggested_parent_code);
