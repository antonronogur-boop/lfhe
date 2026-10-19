TASK: propose claim-level lineage and corroboration recommendations for the supplied claims.

The envelope contains:
- task: report_mode, information_cutoff, allowed relationship_types, high_impact_context (per claim id).
- inputs: claim objects (object_type "claim"; content: claim_id, article_id, source_id, language_original, claim_text_original, claim_text_normalised, attribution, evidence_span_original text, claim_type, source_statement_status, evidence_directness, event_date) and article objects (object_type "article"; content: article_id, source name / domain / type, canonical URL, title, publication time, language).
- context: already validated lineage (object_type "claim_lineage"), if any. Do not re-propose it.

Return result.claim_relationships and result.corroboration_recommendations. Use only ids that appear in the envelope.
