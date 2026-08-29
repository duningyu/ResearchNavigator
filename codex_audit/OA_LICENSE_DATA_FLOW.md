# OA license data flow

For DOI `10.1177/20552076241297729`, the frozen implementation flow is:

1. `OpenAlexOpenAccessClient.resolve()` in `apps/api/research_navigator/open_access/openalex.py` reads each OpenAlex location's `license` field and constructs an `OpenAccessCandidate(license=location.get("license"), ...)`.
2. `OpenAccessCandidate` in `apps/api/research_navigator/open_access/base.py` carries `license` and `normalized_license` separately, preserving the provider value before policy normalization.
3. `resolve_candidates()` in `apps/api/research_navigator/open_access/resolver.py` applies `decide_access()` to each candidate and retains candidate-level provenance rather than overwriting provider records.
4. `decide_access()` in `apps/api/research_navigator/open_access/policy.py` calls `normalize_license(candidate.license)`. `CC BY-NC 4.0` and the OpenAlex value `cc-by-nc` normalize to `cc-by-nc`; that value is in `_LIMITED`, so the decision is `requires_user_confirmation` with reason `limited_license_requires_confirmation`.
5. `PaperSource` in `apps/api/research_navigator/models.py` stores provider identity (`source`, `source_id`, `source_url`, `raw_hash`) but has no license column. The live CASE B result therefore correctly has no PaperSource license value; license remains on the OA candidate/policy evidence.
6. `PaperDocument.license` is populated only by `ingest_candidate()` in `apps/api/research_navigator/open_access/ingestion.py`, after permitted ingestion. Because CASE B was not confirmed, no PaperDocument was created and no document license was persisted.

The historical `cc-by`/`CC BY-NC 4.0` appearance is a representation/source distinction, not a conversion from NC to BY: the fixed manifest and Crossref/PMC evidence use the human-readable `CC BY-NC 4.0`, while OpenAlex and the selected candidate use the canonical token `cc-by-nc`. The selected candidate and policy input both retain the NC restriction.
