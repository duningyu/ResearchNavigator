# OA license provenance audit

Status: PASS — no second license bug found.

Crossref reports the URL form `https://creativecommons.org/licenses/by-nc/4.0/`;
OpenAlex reports `cc-by-nc`; and the fixed manifest/PMC evidence reports
`CC BY-NC 4.0`. These are equivalent representations of the same restricted
license, not `CC BY`.

ResearchNavigator selected an OpenAlex candidate with `license=cc-by-nc`,
normalized it to `cc-by-nc`, and applied `requires_user_confirmation`.
`PaperSource` stores provider provenance but has no license field; the
document license field is only populated after permitted ingestion. CASE B
was not ingested and evidence was not promoted.

Semantic Scholar was rate limited and was not used to override the consistent
Crossref/OpenAlex/PMC evidence.
