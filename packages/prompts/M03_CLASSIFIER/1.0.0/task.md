TASK: classify every supplied claim against the supplied closed taxonomy.

The envelope contains:
- task: taxonomy_version, intelligence_requirements (the PIR identifiers in scope).
- inputs: one object per claim (object_type "claim", object_id = the claim's id); content has claim_id, claim_text_normalised, claim_text_original, language_original, claim_type, attribution, entity mentions, locations and event_date.
- context: one taxonomy object (object_type "taxonomy", object_id = taxonomy_version) listing every allowed item with id, taxonomy_type, label and description.

Return result.assignments (target_object_id = the claim's id) and result.classification_confidence.
