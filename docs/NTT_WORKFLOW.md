# NTT workflow improvements

## Local review flow

1. Create or open an investigation. Intake parses locally by default; review the context manually.
2. Open **Solution workspace**. The lifecycle summary assembles recorded information without generating claims. Imported notes remain distinct from new stage completion evidence.
3. Enter SAP applicability: plant, transaction, program/include, enhancement, configuration path and affected process.
4. Record requirements and unanswered questions. Confirmation/rejection requires supporting evidence. Do not resolve the document's vendor-fallback, advisory/error, MRP-tab or repeated-component ambiguities by guessing.
5. Search local knowledge without AI, including Pending sources. Results are keyword matches, not confidence estimates. Only the ticket customer and General sources qualify.
6. Write separate functional and technical proposals. Up to five supporting source quotations are checked against the stored content and customer scope. Citations retain a content hash and section reference. Uncited proposals display an unsupported-draft warning.
7. Update lifecycle stages with owners and evidence. Completion requires evidence; imported history does not automatically complete stages. Stage order is not enforced because client transition rules have not been confirmed.
8. Record verification scenarios with expected results. Passed/Failed results require actual results, environment, tester and evidence.
9. Record consultant evaluations of summary completeness, supported claims and scenario coverage. Each assessment records the ticket revision evaluated; it is a review record, not an automated quality score.
10. Resolve only after outstanding requirements are confirmed/rejected and all recorded scenarios pass. For changes with stage tracking, every change stage must be completed. Existing closure confirmation checks still apply. Historical closed records may receive supplemental workspace evidence without rewriting the imported outcome.

All workspace changes use optimistic revision checks and append a timeline event. This is a local consultant workspace, not an immutable compliance audit system.

## Documents and AI budget

DOCX extraction preserves paragraph/table order and marks Word heading styles. Chunking respects marked section boundaries and retains offsets/section names. Plain paragraphs that visually resemble headings are not automatically inferred as headings. Image-only content still requires separate transcription/OCR.

Knowledge records support document version, section/page, source reference, customer scope and existing review metadata. Saving knowledge defaults to Pending without Gemini calls. Explicit indexing is separate; already Ready documents on the same embedding model reuse their index. Local intake, search, editing and evaluation do not call Gemini. The existing 5/minute and 20/day guard remains unchanged.

The structured consultant workspace is included in subsequent explicit AI analyses. AI-generated combined proposals, query-embedding/result caching and live model quality evaluation are deferred to the AI phase; this implementation does not claim these are tested.

## Validation and deployment boundaries

Unit tests cover source quotation/scope validation, stale revisions, requirement/scenario closure gates, stage completion evidence, deferred indexing, index reuse and document ordering/section chunking. Provider tests use mocks. Browser smoke checks use an isolated in-memory database and disabled AI, exercising requirement/proposal/scenario creation and local search.

No client files, database backups, credentials or browser fixture records are committed. No production records are changed by these tests.

The server remains loopback-only. Customer workspace filters are not authentication. Shared deployment still requires an agreed identity provider, authenticated roles/customer membership, source ACLs and a durable audit strategy. SAP/SharePoint links are provenance only; connectors and independent technical validation are not implemented. Retrieval accuracy and time saved remain unmeasured until NTT supplies or reviews expected answers for evaluation cases.
