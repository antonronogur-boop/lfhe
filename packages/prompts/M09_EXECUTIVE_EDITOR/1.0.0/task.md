TASK: edit the human-selected report material into a draft report version.

The envelope contains:
- task: report_mode, information_cutoff, report_code, cycle_label, selection_set_id, selection_set_hash, section_targets, likelihood_terms (canonical vocabulary, rank order), editorial_transforms.
- inputs: exactly one object_type "report_selection_set" with candidates[] (candidate_id, candidate_type, section, priority, pins, final_analytic_confidence, statements[] with assessment_statement_id, statement_type, epistemic_category, text, attribution_required, attribution_text, likelihood_term, contested, caveat_class; plus indicator or trend text where applicable).
- context: none.
