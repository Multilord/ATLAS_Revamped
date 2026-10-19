# Solution ATLAS — 2 minute 30 second demo script

Audience: client stakeholders and support-management teams.

Duration: 2:30, including navigation and short pauses.

Delivery: speak at approximately 125–135 words per minute; rehearse the click sequence.

## Preparation — before the timer starts

- Sign in with a Consultant account and open Dashboard. Use fictional reference data for the presentation.
- Choose an open investigation that has useful historical references and enough context to explain the issue clearly.
- Prepare one small CSV/XLSX export with non-sensitive ticket fields. Know which customer, title and problem/content columns to select.
- In a separate browser profile, prepare an independent Reviewer account. Do not use two tabs in the same browser profile for different accounts: they share the session cookie.
- Prepare an independently approved source and ticket. If showing a generated AI assessment, run and verify it beforehand, then keep its Recommendations page in a separate tab. Check that it contains valid citations and explainable warnings. Do not describe a prepared example as a live generation.
- Keep the current workflow's security-review panel and an appropriate change request's Approval panel ready in separate tabs if available.
- Avoid live extraction, indexing, connection checks and repeated Refresh actions during the timed presentation. These consume Gemini requests. Playing back saved results, local search and import preview do not.
- If no saved AI assessment exists, use the alternative narration below. Do not imply that an assessment has been generated or validated.

## Timed presentation

| Time | On-screen actions | Spoken narration | Purpose of the action |
|---|---|---|---|
| **0:00–0:15** | Start on Dashboard. Point to active investigations and knowledge sources. | “Support teams often revisit issues with history scattered across tickets and documents. Solution ATLAS brings that evidence together, helping consultants assess what applies to the current customer.” | Establish the business problem and the solution's role. |
| **0:15–0:35** | Open Knowledge. Select a Customer, then Evidence quality. Show the matching sources. | “Knowledge is filtered by customer, origin and evidence quality. We distinguish reviewed fixes, workarounds and unresolved findings: a closed historical ticket does not necessarily contain a permanent solution.” | Demonstrate scoped discovery and evidence quality. |
| **0:35–0:55** | Choose **Upload historical data**, select the prepared export and click **Preview historical data**. Point to mappings, an editable cell and a column-inclusion checkbox. Leave the preview unsaved. | “SAP ticket exports are previewed before saving. Consultants map fields, exclude unnecessary columns and redact sensitive text. Saving and AI indexing are separate actions, giving the team control over incoming knowledge.” | Show controlled ingestion; avoid claiming a live SAP connector. |
| **0:55–1:15** | Close the upload dialog. Open the prepared investigation's **Evidence & Notes** tab. Under Historical references, enter a prepared query and click **Search without AI**. Point to a relevant result and its quality label. | “For an unresolved ticket, consultants search historical references locally without spending AI quota. They can inspect sources and attach supporting quotations. Linking evidence does not automatically accept a solution or close the ticket.” | Show the useful local workflow and the human decision boundary. |
| **1:15–1:40** | Switch to the prepared **Recommendations** tab. Show the saved assessment, one cited quotation, suggested steps and a compatibility warning. Do not click Refresh. | “This is a previously generated assessment. Gemini combines ticket context with permitted evidence to propose investigation steps and clarification questions. Recommendations include quotations and applicability warnings. ATLAS checks citations and reduces confidence for conflicts or incompatible environments. Relevance points are ranking scores, not success probabilities.” | Demonstrate the AI's contribution accurately without depending on provider availability. |
| **1:40–2:00** | Show **Security & AI permission** on the prepared ticket or source. Point to classification, external-AI permission and reviewer identity. If useful, show the review screen in the separate Reviewer browser profile. | “New content starts Restricted, with external AI blocked. An independent reviewer approves eligible content and permits Gemini processing. Screening flags common secrets and suspicious instructions; application code enforces customer permissions.” | Explain data disclosure controls and layered prompt-injection safeguards. |
| **2:00–2:20** | Switch to the prepared change request's Approval panel, then its Outcome tab. Point to the decision attribution and validation fields. If no attributable approval has been recorded, show the Pending state rather than implying approval exists. | “Approvals identify the signed-in approver. Creators cannot approve their own proposals, and changes invalidate approval. Consultants record testing, customer confirmation and outcomes, helping future retrieval reflect observed results.” | Demonstrate attributable approval and the feedback loop. |
| **2:20–2:30** | Return to Dashboard or leave the evidence-backed recommendation visible. Pause briefly at the end. | “ATLAS connects historical evidence, AI-assisted investigation and accountable decisions, while keeping consultants in control of customer data and changes.” | Close on the business value. |

## Alternative at 1:15–1:40 — if no saved AI assessment is ready

Stay on the investigation's Overview and show the **Search historical evidence** action without clicking it.

> “The next stage is AI-assisted investigation. Once the ticket and sources have approval for external processing, ATLAS can retrieve indexed evidence and ask Gemini for recommendations, clarification questions and validation steps. Each recommendation must cite a supplied passage. We are showing the workflow today; we are not claiming a generated result for this ticket.”

Use the remaining seconds to point to application, platform and release context. Continue with the security segment at 1:40.

## Presenter notes

- This is an **export-based SAP ingestion workflow**, not a demonstrated live SAP integration.
- A recording or saved result should always be identified as prepared. Generated steps still require consultant review and testing.
- Do not say that all prompt injection is detected, that screening detects all personal data, or that citations prove the proposed procedure is correct.
- Malware scanning is optional until the scanner is installed and configured. Do not describe an unscanned file as clean.
- Approvals are attributable to authenticated local accounts. Company SSO/MFA remains a separate integration.
- Do not show passwords, setup tokens, API keys, raw client-sensitive documents or production credentials.
- Keep the customer, origin and quality filters deliberate: accidental combinations can produce an empty catalogue during the presentation.
- Local search may return no result if the user's customer memberships or reference-data scope do not permit the source. Prepare a permitted matching example in advance.

## Gemini request planning

| Preparation action | Normal local request count |
|---|---:|
| Manual ticket creation, upload preview, review and local search | 0 |
| Unstructured ticket extraction | 1 |
| Index one source | 1 per up to 16 passages |
| Generate one investigation assessment | Normally 2 |
| View the prepared assessment during the demo | 0 |

The configured default budget remains 5 requests per rolling minute and 20 per UTC day. Prepare only the relevant approved evidence, and avoid repeating live AI actions during rehearsal.
