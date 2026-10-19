# Historical documentation

This feature extends `updated_reqs`; it does not replace its lifecycle, approval, solutioning or outcome workflows.

## Upload and review

On **Knowledge / Sources**, choose **Upload historical data**. CSV and XLSX-family workbooks are parsed into rows; choose a worksheet where applicable and review the column mappings and all records. Map title and problem/content, then review customer, application, platform, module, component, release, document version, original update date, classification and quality. Specify the date order for non-ISO spreadsheet dates. Each row becomes one source, preserving every non-empty original column in the text. Documents such as DOCX, PDF and text become a single editable preview. DOCX paragraph/table order is preserved; scanned PDFs still require OCR.

Imports accept files up to 5 MB, expanded Office documents up to 20 MB, at most 100 records and 120,000 extracted characters per batch. Missing fields or invalid mappings reject the batch before writes. Identical content in the same customer scope is skipped, making retries safe. A database/network failure during saving can leave a partial batch; retry skips the completed rows. Original dates are never inferred from import time.

Classifications: Historical ticket, Resolution guide, Investigation report, Known issue and Change record. Qualities: Unreviewed, Reviewed, Verified fix, Workaround and Unresolved findings. Reviewed sources require review notes. Verified fixes require test, customer confirmation and deployment evidence. The app records the consultant's assertions; it does not independently verify the supplied evidence. Closure alone does not prove a fix. Existing source validation and conflict references remain available.

## Reference an open investigation

In **Evidence & Notes**, use **Historical references → Search without AI**. This keyword search includes Pending sources, limits results to the ticket's permitted customer scope or explicitly generalized knowledge, and displays source quality, original date and release. Choose **Attach as evidence**, optionally retain an exact quotation, and explain applicability. Exact quotations are checked against source text. The link stores source ID, content hash, quality snapshot, author and timestamp, and creates a timeline event. It invalidates old analysis but does not select a recommendation, advance lifecycle or overwrite an outcome. Closed lifecycle records cannot acquire new links.

Unresolved findings support diagnosis rather than a confirmed fix. Future explicit AI analyses receive their quality label and cannot label them a verified historical fix; resulting findings are marked low confidence. Workarounds and outdated/conflicting guidance retain their warnings.

## Synthetic library

**Add synthetic reference library** installs 16 fictional documents: four each for expiry-based batch selection, vendor consistency, plant onboarding and repeated-component quantities. Each topic includes a simulated resolution, workaround, unresolved investigation and outdated/conflicting alternative. Simulated verified results are labelled as simulated and do not set real verification flags.

The library is under `ATLAS Historical Demo` in an all-customer installation, or isolated by its synthetic/library markers within a configured customer workspace. Synthetic sources are excluded from real-ticket local search, linking and AI retrieval. Existing tickets labelled `data_origin: Synthetic demo` may use the library. Regular customer-specific uploads still require matching customer scope; merely being synthetic does not expose other customers' documents. Catalogue origin/quality filters make the distinction visible.

Library installation is explicit and insert-only. Repeating it preserves edits, reviews and indexes. It creates no tickets, overwrites no existing source and makes no AI calls.

## AI budget

Saving both historical and ordinary knowledge now defaults to Pending and uses zero Gemini requests. Use **Index / reindex** to inspect the chunk count and estimated requests (one per 16 chunks), local remaining quota, and the text-transfer notice before explicitly confirming. The existing 5/minute and 20/day guard remains in force. Indexing is synchronous; failures preserve source text and can be retried. Each source is indexed independently; no background job or cross-document batch is implied.

Automated regression and browser tests use mocks/in-memory storage. They cover CSV/XLSX preview, mappings, invalid-batch rejection, duplicates, quality checks, scopes, synthetic exclusion, local search, quotes, optimistic revisions, and attaching without changing lifecycle or solution selection. Live Gemini quality and upstream quota remain separate tests.
