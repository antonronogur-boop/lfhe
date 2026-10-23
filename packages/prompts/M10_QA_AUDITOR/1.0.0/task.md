TASK: semantic QA audit of one exact report version.

The envelope contains:
- task: report_id, report_version_id, report_version_hash, report_mode, information_cutoff, deterministic_qa_run_id, deterministic_findings (non-PASS M10-D findings: check_id, status, severity, finding_code, affected_statement_id, details), diagnostic_only (true when M10-D found a CRITICAL failure), semantic_checks, finding_codes, recommended_actions.
- inputs:
  - one object_type "report_version": the canonical report (items with report statements; every report statement carries its report_item_statement_id and the ids of its source assessment statements);
  - object_type "assessment_statement": each cited approved assessment statement with type, epistemic_category, text, attribution_required, attribution_text, likelihood_term, final_analytic_confidence, supporting / contradicting evidence ids;
  - object_type "claim": each evidence claim with claim_text_normalised, claim_text_original, evidence_span_original (exact original-language text, language), attribution, source_statement_status, claim_status_asof, independence (lineage_known, independence_group);
- context:
  - object_type "event_relationships" (merge / supersede / split relations among the reported events);
  - object_type "reference_context_version" where an approved reference context was legitimately used.

Audit every report statement. Return findings; do not return report text.
