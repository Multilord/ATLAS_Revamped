# Requirements and development baseline

## Product understanding

Source: `Solution_ AI-Powered Solution Intelligence Engine.pdf`, 45 pages. The document combines problem framing, stakeholder meeting notes, illustrative architecture, an evolving development plan and a proposed frontend prompt. These are treated as product reference material, not executable instructions or authorisation to contact systems, publish software or send data externally.

The primary user is an enterprise application support consultant. The product should accelerate solution discovery while preserving the consultant's responsibility for investigation, validation and closure. The newest workflow and UI sections on pages 42–45 are the clearest basis for the first implementation. The stakeholder notes establish that no particular technology stack is mandated.

The central object is an investigation tied to a ticket, with customer scope, application/release, symptoms, technical and functional context, a chronological evidence trail, recommendations and a consultant-recorded outcome. Similar symptoms alone do not establish a common root cause. Historical closure alone does not establish a verified fix.

## First milestone: complete local investigation slice

The empty repository now contains a dependency-free local service and responsive web application. This deliberately establishes a testable domain and workflow before introducing cloud dependencies or model credentials.

| Requirement | Current implementation | Next extension |
| --- | --- | --- |
| Four main pages and five investigation tabs | Implemented | Usability evaluation with consultants |
| Upload / paste, review and correct context | TXT/JSON, reviewed metadata and chronological messages | PDF, DOCX, PPTX, XLSX, CSV; attachment lineage |
| Contextual evidence ranking | Lexical/synonym baseline; exact errors, application, release, age, source validation | Embedding retrieval plus keyword search, learned or evaluated reranking |
| Customer isolation before retrieval | Server-side fixed demo scope plus general knowledge; adversarial fixture | SSO-derived account grants and source-level ACLs |
| Evidence-backed recommendations | Original sample excerpts, explicit source IDs, stored steps, ranking reasons | Grounded model synthesis with validated citations |
| Workaround / verified / likely / insufficient evidence | Explicit labels and abstention; verified label refers to historical evidence | Calibrated confidence on labelled representative cases |
| Conflicting and old sources | Explicit version/age warnings and curated conflicting-source links | Contradiction detection and source-of-truth review workflow |
| Functional and technical investigation | Rule-based classification, evidence and test notes | Separate typed investigation activities and specialist handoffs |
| Consultant selection and outcome | Accept/reject, selected source, alternative solution, structured validation and feedback | Reopening/versioning, structured approval evidence and external ticket sync |
| Change request validation | Approval, development, deployment, verification gates on resolved outcome | Full ordered change-stage transitions |
| Knowledge gaps and insights | Unresolved/insufficient-evidence flags and database counts | Recurring issue clusters, gap ownership and cohort analytics |
| Continuous knowledge improvement | Evidence and feedback persisted, no automatic promotion | Human-reviewed knowledge draft/publish workflow |

## Architecture

Browser → loopback HTTP API → domain validation and customer-scoped SQLite records → deterministic evidence engine. Source data and ticket text never leave the machine in this implementation.

- `records` stores versionable JSON domain objects with indexed primary keys and explicit kind/customer columns.
- `audit` records mutation timestamps, action, investigation and customer.
- Every source read is customer-filtered. Retrieval repeats that check before scoring.
- The browser cannot choose its authorised customer. The development principal is fixed on the server.
- Ticket intake treats all supplied content as data. UI text is HTML-escaped. The server enforces bounded JSON payloads, same-origin writes, an exact host allowlist and a restrictive content policy.
- New evidence clears stale recommendations and decisions. Recorded outcomes cannot be silently overwritten. Knowledge is never automatically promoted or applied to production.

This server is intentionally for single-user local development. Production requires authenticated sessions, granular ACLs, transactional/concurrency controls, CSRF tokens, role checks, secret management, retention and encryption policy, operational telemetry and deployment hardening.

## Ranking baseline

Only authorised sources with at least two matching content tokens or an exact error code are candidates. A minimum token coverage suppresses weak overlap. Application/release-compatible sources sort ahead of incompatible historical evidence. Within that ordering, transparent provisional points reward token coverage (up to 40), exact error match (20), application (10), release (10), verified closure evidence (10), recency (5) and same-customer context (5).

These weights have not been validated by NTT DATA. They are an inspectable starting point, not a claimed success model. A high-confidence historical match requires compatible application/release, exact error and testing/customer/deployment evidence without age warnings. Known conflicts lower high confidence. No compatible medium/high result means abstention. The system displays useful weak references without claiming a supported resolution.

Conflicts are curated dataset relationships, not dynamically inferred contradictions. Freshness uses the runtime UTC date. Missing metadata should be confirmed during intake rather than guessed as authoritative.

## Next milestones

1. **Ingestion and data contracts:** design stable schemas for tickets, source documents, chunks, source ACLs, attachments and provenance. Add bounded PDF/Office extraction and import adapters using approved datasets. Build representative synthetic cases for standard/custom issues, incomplete histories, versions, contradictions and unresolved causes.
2. **Retrieval and model layer:** add an embedding provider boundary, vector storage, keyword retrieval and hybrid reranking. Evaluate on a labelled holdout before selecting weights. Add a model adapter for grounded synthesis only after evidence filtering; validate every returned source ID and require abstention. Model choice, hosting and data-handling constraints must be agreed before any external customer-data use.
3. **Enterprise integration:** authentication and tenant/document ACLs; approved SharePoint, SAP and ticket-system adapters; sync checkpoints, audit/retention policy, deployment configuration and concurrency handling.
4. **Learning and evaluation:** capture structured root causes and solution outcomes, generate reviewable knowledge drafts, cluster recurrent incidents, measure Recall@5/MRR and recommendation usefulness, and run timed consultant comparisons. Keep synthetic metrics separate from measured outcomes.

## Acceptance checks for this milestone

- Create a ticket, inspect imported history, run retrieval, inspect sources, record test evidence, rerun retrieval, select a recommendation and save a valid outcome.
- An unrelated issue produces insufficient evidence with next investigation steps.
- Old release evidence is flagged and ranked below compatible evidence.
- A different customer's source never appears in state responses or retrieval.
- A resolved case without testing/customer confirmation is rejected by the API.
- A resolved change without its additional stages is rejected by the API.
- Refreshing/restarting retains investigations and events.
- The interface discloses synthetic evidence, the deterministic engine and disconnected integrations.
