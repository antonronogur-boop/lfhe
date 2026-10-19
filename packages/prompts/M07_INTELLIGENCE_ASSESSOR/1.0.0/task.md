TASK: draft the assessment of the supplied event version.

The envelope contains:
- task: report_mode, information_cutoff, event_id, event_version_id, event_version_hash, baseline_version_id + baseline_status, previous_assessment_version_id, reference_context_version_ids, likelihood_terms, independence_summary (as of the cutoff), statement_types, provenance_classes.
- inputs: exactly one object_type "event_version" with its claims (text, attribution, claim_type, source_statement_status, as-of claim_status, role, high_impact, independence_group, attribution_required_if_cited).
- context: "baseline_version", "reference_context_version", "assessment_version" (previous approved) and "claim_lineage" objects, only when eligible for the cutoff.
