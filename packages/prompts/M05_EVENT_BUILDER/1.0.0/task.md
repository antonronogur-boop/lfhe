TASK: propose event-structure changes for the supplied new claims.

The envelope contains:
- task: report_mode, information_cutoff.
- inputs: claim objects (object_type "claim"; content: claim_id, claim_text_original, claim_text_normalised, attribution, claim_type, event_date, location mentions, entity mentions, language_original, independence group).
- context: candidate existing events, one object per event's CURRENT version (object_type "event_version"; content: event_id, version_id, version_no, state, title, description, event_type, dates, locations and its eligible claims with roles), and validated claim lineage (object_type "claim_lineage").

Return result.proposals. Use only ids that appear in the envelope.
