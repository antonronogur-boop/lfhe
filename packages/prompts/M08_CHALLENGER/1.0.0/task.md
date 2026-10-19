TASK: challenge the supplied assessment version.

The envelope contains:
- task: report_mode, information_cutoff (those of the assessment version), assessment_version_id, assessment_version_hash.
- inputs: exactly one object_type "assessment_version" (statements with local ids, types, text, provenance class, evidence ids, attribution, likelihood, premises; ai_recommended_confidence + rationale; derived summary; indicators_to_watch).
- context: the "event_version" with its claims, "baseline_version", "reference_context_version" and "claim_lineage" objects used by the draft (only when eligible for the cutoff).
