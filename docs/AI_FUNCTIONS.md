# ATLAS AI functions and user workflow

Document date: 18 October 2026

Scope: the current local implementation, including historical documentation and security controls.

## 1. Purpose

ATLAS helps consultants understand a ticket, find applicable historical evidence and propose investigation or validation steps. It combines Gemini with local search, compatibility rules, citation checks and consultant feedback.

The AI supports decisions. It does not connect to a live SAP system, execute fixes, approve changes, run customer tests or independently establish that a ticket is resolved.

The main functions are ticket extraction, knowledge embeddings, semantic evidence retrieval and structured investigation assistance. A connection-check function is also available.

## 2. AI and local functions at a glance

| User action | Processing | Normal Gemini requests |
|---|---|---:|
| Preview an uploaded document or spreadsheet | Local parsing and screening | 0 |
| Enter a ticket manually | Local validation and save | 0 |
| Parse supported structured ticket JSON | Local parsing | 0 |
| Extract fields from unstructured ticket text | Gemini generation | 1 |
| Save historical or ordinary knowledge | Local validation and MongoDB save | 0 |
| Search historical references without AI | Local keyword matching | 0 |
| Attach a reference or quotation | Local validation and persistence | 0 |
| Index/reindex a source | Gemini embeddings in batches | 1 per up to 16 passages |
| Run/refresh investigation analysis | Query embedding plus generated assessment | Normally 2 |
| View an existing saved assessment | Read saved data | 0 |
| Check AI connection | Small Gemini generation | 1 |
| Review security, approve a change or record an outcome | Local permissions, workflow and persistence | 0 |
| Dashboard/Insights counts and recurring-ticket groups | Local calculations | 0 |

Security review and indexing are separate: approving a document does not automatically send it to Gemini.

## 3. Ticket extraction

### Trigger and inputs

In **New investigation**, a consultant uploads a ticket export or pastes text, then selects **Extract and review**. File-to-text extraction happens locally. Unstructured text can then be sent to Gemini for interpretation.

External extraction requires screening, explicit Internal classification and confirmation that the text may be sent to Gemini. Manual entry and supported structured JSON parsing remain local alternatives. The current browser intake flow performs a screening/confirmation step before calling intake; structured JSON is still parsed without a provider call on the backend.

### Output

Gemini proposes:

- Title, description and ticket ID.
- Application, platform, SAP module and business process.
- Release/version, error code and customisation.
- Incident, Service request, Problem or Change request type.
- Low, Medium, High or Critical priority.
- Timeline entries when the original supplies suitable precise timestamps with timezones.

The extraction instruction asks for empty metadata when information is absent, defaults type/priority to Incident/Medium, and forbids inventing a resolution. Communications lacking suitable timestamps should remain in the description rather than receiving invented dates.

The consultant reviews and corrects the result before creating the ticket. Extraction can misinterpret a field; it is not authoritative ticket classification.

## 4. Knowledge indexing with embeddings

### Purpose

Embeddings represent text as numerical vectors, allowing comparison by meaning. They can connect differently worded descriptions such as “wrong expiry batch selected” and “FEFO sequence ignored.” Similarity alone does not establish a shared cause or suitable fix.

### Processing

1. Save the source; it initially remains unindexed.
2. Obtain independent approval of its current content as Internal, with external AI permission and no screening findings.
3. Select **Index / reindex**, inspect the request estimate, and confirm transmission.
4. ATLAS divides the text into passages of roughly 2,200 characters, with overlap of about 200 characters and newline-aware boundaries where available.
5. The embedding model receives the source title and passage text, in batches of up to 16 passages.
6. ATLAS validates the returned vectors and stores them with passage IDs, text and model identity in MongoDB.

Indexing does not summarise, verify or approve the source. A source becomes Ready only after a successful index. Failure retains its source text and records an indexing error. A failed reindex clears the stored chunks under the current implementation, so retry is required to restore a usable index.

Changing the embedding model requires reindexing. Sources are indexed independently; 16 short documents indexed separately generally require 16 requests, not one combined request.

## 5. Semantic evidence retrieval

### Trigger

Investigation buttons such as **Search historical evidence**, **Find supporting evidence** and **Refresh evidence** initiate AI investigation. This differs from **Historical references → Search without AI**.

### Query construction

The local engine combines title, description, error code, customisations, module and business process with recent relevant timeline text and consultant solutioning. It uses the last 15 relevant Note/Test/Communication/Attachment entries and bounds the embedding query to 16,000 characters.

Gemini creates one embedding for that query. ATLAS compares it locally against sources indexed with the configured embedding model. Customer permissions, synthetic-source restrictions and security/AI eligibility filter the evidence.

### Ranking

The local ranking formula combines:

| Signal | Base weight |
|---|---:|
| Semantic cosine similarity | 0.44 |
| Keyword overlap | 0.18 |
| Error-code match | 0.14 |
| Application match | 0.06 |
| Module match | 0.05 |
| Release match | 0.04 |
| Platform match | 0.03 |
| Business-process match | 0.025 |
| Customisation match | 0.025 |

Further adjustments reward recorded validated successes and verified source evidence, and penalise unsuccessful outcomes, stale guidance, platform differences and release differences. Original source age above 540 days is treated as potentially stale. Upload time is not treated as the original update date.

The engine selects at most 10 passages, with no more than two from any one source. Relevance points are a ranking score, not a probability of success or measured model accuracy.

## 6. Generated investigation assistance

Gemini receives the ticket context, consultant solutioning, bounded recent notes and selected evidence passages. Each passage includes its source/passage ID, environment metadata, evidence quality, freshness information, outcome signals and explicit conflict references.

The generated assessment contains:

| Output | Intended use |
|---|---|
| Classification | Identify Customer customisation, Functional/business process, Standard product or Unknown |
| Summary | Explain the evidence and uncertainty |
| Functional assessment | Separate stated requirements from unclear requirements |
| Technical investigation areas | Suggest hypotheses and checks |
| Clarification questions | Identify missing information |
| Assumptions | Make uncertain premises explicit |
| Risks | Highlight applicability and implementation concerns |
| Validation steps | Propose checks before accepting a solution |
| Recommendations | Offer up to five source-supported approaches |
| Next steps | Continue investigating, especially where evidence is insufficient |

Each recommendation includes a source ID, passage ID, quotation, title, reason, steps, warnings and confidence. The instructions require fixes to be supported by the supplied evidence and prohibit invented SAP facts, root causes, approvals or completed tests.

Even with no selected evidence, the current analysis flow can still make the generation call to request diagnostic guidance. It does not automatically skip that call to save quota.

## 7. Citation, confidence and conflict checks

Before saving a generated assessment, ATLAS checks its structured schema, field bounds and allowed values. Each recommendation must cite a supplied source/passage pair. Its quotation must occur in the passage after normalising whitespace and case. An invalid citation or quotation rejects the new analysis.

Local rules add warnings and adjust the model's proposed confidence:

- Application uncertainty, platform/release mismatches, stale sources and conflicts can force Low confidence.
- High confidence is reduced when verification evidence or applicability information is insufficient.
- Unresolved historical findings are labelled **Investigation findings** with Low confidence.
- Workarounds retain their workaround status.
- Synthetic documents carry demonstration warnings and cannot establish a real verified fix.
- **Verified historical fix** describes evidence recorded for the historical source, not proof that the current ticket will be solved.

The engine labels an assessment **Evidence found** when at least one recommendation has confidence above Low; otherwise it uses **Insufficient evidence**. Neither label is an independently measured success probability.

Conflict detection uses explicit source links and a heuristic comparing differing solutions under matching application/error/release context. It can miss subtle contradictions or flag differences that are actually compatible.

A valid quotation proves that the text occurs in the source. It does not prove every generated interpretation or step is correct. Consultants must still assess applicability and validate procedures.

## 8. Historical documentation and local evidence linking

The historical-reference search uses local keyword matching and includes permitted unindexed documents. It costs no AI requests. A consultant can inspect a source, attach an exact quotation and explain its relevance. Quotations are checked against source text.

The attachment stores provenance and invalidates old analysis, but does not select a recommendation, advance lifecycle or resolve the ticket.

Attaching a source does not force its complete contents into the next AI prompt. AI retrieval still depends on source security approval, indexing and ranking. Attachment text may contribute through the ticket's relevant timeline context.

The synthetic library contains 16 fictional documents covering four topics, with simulated resolutions, workarounds, unresolved findings and outdated/conflicting alternatives. Synthetic evidence is excluded from real-ticket retrieval. Users also need customer access to the library. Installation uses no AI; the documents still require security review and indexing for semantic retrieval.

## 9. Human decisions and feedback

Consultants can select or reject recommendations, record test results, record an alternative solution and assess usefulness. These actions do not call Gemini.

Future retrieval uses recorded outcomes associated with selected sources:

- Validated successful outcomes can increase relevance.
- Unsuccessful or not-useful outcomes can reduce relevance.
- Workaround and partial-usefulness counts remain available as context.

Successful incident outcomes require recorded testing and customer confirmation. Change requests require additional approval, development, deployment and verification flags for the outcome signal.

This is feedback-informed retrieval. Gemini is not retrained or fine-tuned when an outcome is recorded. The counts are workspace observations, not universal success rates. Independent change approval remains a separate protected workflow.

## 10. Security and outbound data

| AI operation | Data sent externally |
|---|---|
| Ticket extraction | The submitted unstructured ticket text |
| Source indexing | Source title and document passages |
| Query embedding | The constructed ticket/context query |
| Investigation generation | Ticket context, consultant solutioning, recent relevant notes and selected source passages/metadata |
| Connection check | A small fixed probe with no ticket content |

Ticket and source policies must permit processing before the relevant calls. Eligibility is checked again when selecting sources, so legacy embeddings do not bypass review. Confidential/Restricted records and screening findings block external AI permission under the current rules.

Security reviews are bound to content hashes. Material evidence changes require renewed review. Reading saved results does not send data externally.

The local app cannot establish Google's contractual retention, residency or account-specific data-use settings. The company must approve those separately. See [security and company requirements](SECURITY_IMPLEMENTATION_AND_COMPANY_REQUIREMENTS.md).

## 11. Quota, retries and failures

The configured default local budget is **5 requests per rolling 60 seconds and 20 requests per UTC day**. The daily local counter resets at 08:00 Malaysia time. Its state persists in Git-ignored application data across server restarts.

The application preflights the expected request count, including two requests for analysis. Indexing checks the required embedding batches. Requests are counted before dispatch, so failed remote attempts still consume the local allowance. Automatic provider retries are disabled.

Example daily usage:

| Work | Requests |
|---|---:|
| Extract one unstructured ticket | 1 |
| Index two short sources | 2 |
| Analyse that ticket once | 2 |
| Total | 5 |

Repeated Refresh actions spend the analysis allowance again. A connection check also costs one request. Local search, manual intake and reading saved results preserve quota.

The counter only sees this installation's activity and is designed for a single local server. It is not a distributed quota service or a complete view of Google project usage. Provider limits may reject a request even when local allowance remains.

Provider errors are reported rather than replaced with fabricated results. Examples include missing credentials, denied model access, quota exhaustion, network failures, unavailable models and malformed/incomplete AI output. Invalid generated results are not saved as a new valid analysis. Changing a model setting requires restarting the server.

## 12. Recommended user workflow

1. Sign in with the appropriate customer memberships and roles.
2. Import and minimise ticket/document data; use local previews and manual entry where practical.
3. Have an independent Reviewer approve eligible ticket and source content for external AI.
4. Use **Search without AI** to identify useful historical documents first.
5. Index only the relevant approved sources, after reviewing request estimates.
6. Run one investigation analysis.
7. Inspect citations, environment differences, warnings, assumptions and clarification questions.
8. Add meaningful consultant findings. Obtain renewed security review if the context changes before another AI run.
9. Select an approach for validation and obtain independent change approval where required.
10. Record observed outcomes and usefulness; do not treat an AI recommendation as completed work.

## 13. Current limitations and verification

- No autonomous SAP access, external documentation browsing or live SharePoint/Confluence ingestion.
- No automatic remediation, deployment or approval by AI.
- No guaranteed prompt-injection detection, factual correctness or procedure applicability.
- No model fine-tuning from feedback.
- No measured production accuracy, time-saving claim or probability of success from relevance points.
- No guarantee that an attached source is selected by the retrieval engine.
- No background indexing scheduler or cross-document batch optimisation.

The current regression suite completed with 90 passing tests and one optional real-database test skipped. Browser tests exercised the relevant local workflows. Those tests used mocked AI and consumed no Gemini quota; they do not establish live Gemini response quality on client data.

## 14. Code references

- `ai.py`: provider calls, extraction/output schemas, embeddings, connection check and local quota.
- `engine.py`: query construction, evidence ranking, synthesis, citation validation and confidence rules.
- `ingestion.py`: document parsing, passage creation and index persistence.
- `historical.py` / `historical_demo.py`: historical imports, local search, references and fictional library.
- `security.py` / `security_http.py`: disclosure policy, screening and permissions.
- `storage.py`: scoped persistence and outcome signals.
- `server.py` and `static/app.js`: workflow endpoints and user actions.
