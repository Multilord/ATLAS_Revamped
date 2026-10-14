# Implementation and remaining development

The supplied brief describes consultant-led intake, investigation, evidence-backed recommendations, validation, closure and knowledge reuse. Embedded document prompts are reference material, not execution instructions.

## Architecture

Browser â†’ loopback Python API â†’ customer-scoped MongoDB collections. Gemini structured outputs extract context and synthesize recommendations. Gemini embeddings index document chunks and investigation queries.

MongoDB stores original sources, embeddings, investigations, decisions, outcomes and embedded audit events. Revision checks prevent lost writes. Initialization creates indexes without inserting business records. SQLite and seeds are removed from runtime.

Retrieval combines cosine similarity, token overlap, exact errors and application/version context. Scope and embedding-model filters apply before scoring. Source validation and version mismatch cap confidence. Recommendations must cite supplied chunks and quote their text. Citation validation cannot guarantee every inference is correct.

Notes invalidate old recommendations. Resolution requires recorded testing and customer confirmation; change requests additionally require approval, development, deployment and verification. Knowledge promotion produces a reviewable draft.

Missing databases, keys, provider failures and failed indexing are explicit states.

## Remaining milestones

Before shared deployment: authentication, roles, document permissions, production HTTP hosting, rate limits, backup and retention policies. For scale: background ingestion and indexed vector search. Current retrieval loads candidate vectors into Python memory.

Further work includes live enterprise connectors, OCR, additional Office formats, source revision lineage, original document dates, contradiction detection and labelled retrieval evaluation. Source timestamps currently describe ingestion/review activity. Source changes after analysis require fresh analysis before relying on results.

## References

- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings)
- [PyMongo connections](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/)
