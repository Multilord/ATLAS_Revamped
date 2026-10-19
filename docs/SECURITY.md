# Local security controls

This version requires local accounts. It remains a loopback-only application; it is not an approved production deployment. No live Gemini calls are needed to configure or test security.

## First sign-in

1. Start MongoDB and `python server.py`.
2. Open the app. If no accounts exist, the server creates `data/bootstrap-token.txt` (Git-ignored).
3. Read that file locally and enter the single-use token, your name, username and a password of 12–256 characters. Do not share the token or commit it.
4. Initial setup creates the first administrator, also assigned Consultant, Reviewer and Approver roles. In a multi-customer installation, this bootstrap account is assigned the customer scopes already present in the local database. Newly added customer scopes are not automatically granted.
5. Use **Users & audit** to create separate named accounts with explicit roles and customer memberships. Share initial passwords privately; users can change their password through **Account**. Password changes revoke all sessions. Disabling an account revokes its sessions.

There are no default accounts or passwords. Setup is single-use and its token file is deleted after success. A user with local filesystem/database access is outside this application's security boundary. Administrative database recovery should be performed by the system owner, not by exposing an unauthenticated reset endpoint.

## Roles and scope

- Viewer: read records within assigned customer scopes.
- Consultant: create and revise tickets/documents, local evidence searches, indexing and AI actions, lifecycle progression, consultant findings and outcomes.
- Reviewer: independent security review and source validation.
- Approver: independent change-request approval decisions.
- Administrator: create/disable users and inspect security events. It does not implicitly grant other roles.

Roles may be combined, but creator/editor identity checks still block self-review and self-approval. Memberships are explicit customer names; `All` and `My Workspace` do not grant wildcard access to signed-in users. General sources require de-identification confirmation, and ordinary users see them only after approval as Internal. Reviewers can inspect pending General documents for review.

All API reads require a valid session. Writes also require a session-specific CSRF token and an allowed role. Sessions use random tokens stored as hashes, HttpOnly/SameSite=Strict cookies, an 8-hour absolute lifetime and a 30-minute idle lifetime. Passwords use salted scrypt. Login attempts are limited by account and client. Role/account status is reloaded on each request. The cookie is intentionally not marked Secure on the local HTTP loopback server; a company HTTPS deployment must add Secure cookies and an approved reverse-proxy/application-server configuration. This server must remain on 127.0.0.1.

## Import and document review

Historical spreadsheets support column exclusion and editable cells before saving. File type and expansion limits are checked. HTTP upload parsing runs in a separate process with a 20-second deadline, up to two concurrent parser jobs, and without inherited application credentials or loading `.env`. This is process isolation, not an OS filesystem/network sandbox. Production deployment should use a restricted parser service/container.

Optional ClamAV integration: set `ATLAS_CLAMSCAN_PATH` to the absolute path of an installed, maintained `clamscan` executable. Set `ATLAS_REQUIRE_MALWARE_SCAN=1` to fail closed if the scanner is absent. Scanner rejection, failure or timeout blocks parsing. Without configuration the UI explicitly reports that no malware scan was performed. Signature updates and scanner installation remain operator responsibilities. Pasted text/direct JSON is screened as content, not sent to a binary malware scanner.

New records start **Pending review / Restricted / external AI blocked**. Existing records without a policy also fail closed for AI. They remain available locally to authorised customer members. An independent Reviewer inspects text and metadata, chooses Internal/Confidential/Restricted, records a decision and review notes, and may explicitly permit external AI for Internal content only. Rejected or unreviewed documents are not eligible for AI retrieval.

Security screening flags common credential assignments, private-key headers, credential-bearing connection URLs, email addresses, suspicious instruction patterns and hidden direction/control characters. Findings block external AI approval. These are heuristic indicators, not complete PII or prompt-injection detection. Reviewers must inspect content and establish company permission to send it externally.

Each review binds to a content/context hash and reviewer identity. Changing content invalidates approval; changing source text clears embeddings and validation. **Review / redact text** revises a document or ticket and records a reason. This editor is not complete erasure: old ticket notes, prior application history or backups can still contain earlier sensitive text. Review all fields and retention locations before claiming data deletion.

## AI boundary

Ticket extraction requires explicit Internal classification and external disclosure confirmation after screening. Structured JSON and manual intake use no AI. Indexing and analysis require approved, unchanged Internal records with external-AI permission; screening is repeated before use. The gate covers ticket descriptions, recent relevant notes, consultant solutioning and source context. Only approved sources can enter AI retrieval, even if legacy embeddings already exist.

Document text never grants permissions, approves a change or executes a command. Existing citation validation and escaped output remain in place. Prompt injection cannot be guaranteed to be detected; independent review, strict retrieval scope and server-side authorization constrain the consequences. Quotas remain 5/minute and 20/day, with no added background AI jobs.

## Attributable approvals

Entering the Approval lifecycle stage always creates Pending status. An Approver who is not the ticket creator or current proposal author records the decision separately. Decisions include account ID, display identity, server timestamp, notes, proposal hash and record revision. Proposal changes invalidate an Approved decision and preserve prior decisions in history. Development/deployment/verification transitions require the approval to match the current proposal. Legacy approvals without an authenticated actor and proposal hash cannot satisfy this gate.

Consultant outcome checkboxes are observations; they do not replace this independent change approval. Users may still record explicit cancellation/escalation exceptions according to the existing lifecycle workflow.

## Audit and limits

Security events record logins, denied API operations, API reads, user management, review intentions and record write intentions/completions. They contain identifiers, hashes and outcomes, not passwords, session tokens or full document bodies. The administration screen shows the latest 200 events. Records identify actors independently of editable display names.

Events have no application edit/delete endpoint, but a database administrator can modify them. They are not tamper-proof or a distributed transaction with the business write; a completed mutation followed by an audit-storage failure can be reported as an error. For production, use restricted database service accounts, transactional/outbox audit delivery and an external append-only logging destination.

Company SSO/MFA, direct SAP integration, provider/data-residency approval, production TLS, database encryption/backups, full data retention/erasure, an OS parser sandbox and external audit infrastructure are not configured by this implementation. No security certification or penetration-test claim is made.

## Verification

`python -m unittest discover -s tests` includes authenticated HTTP tests, session expiry/revocation, role and CSRF denial, customer isolation, independent approval, invalidation after edits, injection/secret screening and proof that blocked AI operations never reach the mocked provider. Browser checks cover sign-in, account creation, upload/import, local evidence linking and independent document review.
