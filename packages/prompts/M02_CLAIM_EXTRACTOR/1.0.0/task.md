TASK: extract claims from the single text_representation input in the envelope.

The envelope contains:
- task: article_snapshot_id, text_representation_id, report_mode, high_impact_context {high_impact, high_impact_reasons}.
- inputs[0].content: article_id, article_snapshot_id, text_representation_id, source_id, title, language_original, content_original (authoritative original-language text; offsets are Unicode code points into this exact string), content_working_translation (null or auxiliary only), publication_datetime, public_availability_datetime, system_retrieval_datetime, source_metadata.
- context: supplied context objects, if any (use only for potential_contradiction flags).

Return result.article_snapshot_id and result.text_representation_id exactly as supplied, and result.claims following the system rules. Number claims C1, C2, ... in order of appearance.
