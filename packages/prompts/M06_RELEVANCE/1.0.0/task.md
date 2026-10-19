TASK: relevance triage of the supplied event version.

The envelope contains:
- task: report_mode, information_cutoff, event_version_id, event_version_hash, baseline_version_id (or null; baseline_status BASELINE_UNAVAILABLE when none is eligible), previous_assessment_version_id (or null), pir_definitions [{id, label, definition}], hu_nato_dimensions [codes].
- inputs: exactly one object_type "event_version" (title, description, event_type, dates, locations, as-of state, claims with text, attribution, claim_type, source_statement_status, as-of claim_status, role).
- context: the baseline version (object_type "baseline_version") when one is eligible.

Return result for that event version only.
