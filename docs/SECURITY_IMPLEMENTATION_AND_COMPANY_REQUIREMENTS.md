# ATLAS security implementation and company requirements

Document date: 18 October 2026

Scope: the local application on `codex/historical-documentation`, based on `updated_reqs`, including the historical documentation and security changes.

This guide explains implemented controls, the user workflow, and what the company must provide before a production deployment. It describes application behaviour; it is not a security certification or penetration-test report.

## 1. Current deployment status

ATLAS runs on `127.0.0.1:8000`, with MongoDB as its datastore and Gemini as its optional external AI provider. It uses local user accounts. It has no configured company SSO, direct SAP connector or production hosting environment.

The security implementation addresses three concerns:

1. Controlling how SAP ticket exports enter the knowledge base and reach Gemini.
2. Limiting risks from harmful files and prompt instructions embedded in documents.
3. Recording approvals against authenticated accounts and specific proposal versions.

## 2. Identity, sessions and customer access

### Implemented

- Sign-in is required for workspace data and operational APIs. Public assets and the initial authentication/setup endpoints remain accessible before sign-in.
- Passwords are stored using salted scrypt hashes, rather than plaintext.
- Sessions use random tokens; the database stores their hashes. Cookies are HttpOnly and SameSite=Strict.
- Sessions expire after eight hours, or after 30 minutes without authenticated activity.
- State-changing authenticated requests require a session-specific CSRF token.
- Failed login attempts are limited by account and client address.
- Account status and roles are reloaded for each authenticated request.
- Password changes revoke all the user's sessions. Administrators can disable an account and revoke its sessions.
- Each user receives explicit customer memberships. Backend reads and writes enforce these memberships, including direct requests for a record ID.

`All` and `My Workspace` are not wildcard customer permissions for signed-in users. General knowledge requires de-identification confirmation. Ordinary users see General documents only after security approval as Internal; Reviewers can inspect pending General documents.

### Roles

| Role | Responsibility |
|---|---|
| Viewer | Read records within assigned customer scopes |
| Consultant | Import and revise records, search evidence, initiate permitted AI operations, record findings and progress workflows |
| Reviewer | Independently review security classification, external AI permission and source validation |
| Approver | Independently decide change-request approvals |
| Administrator | Create or disable accounts and inspect security audit events |

Roles may be combined. Administrator does not automatically grant the other roles, although the initial bootstrap administrator receives all operational roles. Combining roles does not bypass the self-review and self-approval checks.

### Initial setup

1. Start MongoDB and the application.
2. If there are no accounts, the server creates the Git-ignored file `data/bootstrap-token.txt`.
3. Read the token locally and enter it in the first-account screen with your name, username and password.
4. Setup creates the initial administrator and deletes the token file.
5. Under **Users & audit**, create named accounts for the people performing consulting, review and approval.

In a multi-customer installation, the initial administrator receives the customer scopes already present in the database. Newly introduced scopes are not automatically granted. There are no default credentials.

Local accounts establish which account performed an action. Company SSO and identity-management procedures are needed for stronger assurance that accounts correspond to recognised employees.

## 3. Bringing SAP tickets into ATLAS

### Implemented workflow

**Export from SAP → upload → preview → exclude/redact → save in customer scope → independent security review → optional AI indexing.**

Historical CSV/XLSX previews allow users to exclude columns and edit cells before saving. Document previews allow users to inspect and edit extracted text. Source records retain references, content hashes and import information; fields supplied by an export should be checked for accuracy.

New records begin as **Pending review / Restricted / external AI blocked**. Existing records without a security policy also remain blocked from AI processing. Authorised customer members can still read them locally.

Security classifications currently have the following effect:

| Classification | Local access | External Gemini processing |
|---|---|---|
| Internal | Assigned customer members | Only after independent approval, explicit external-AI permission and passing screening |
| Confidential | Assigned customer members | Blocked |
| Restricted | Assigned customer members | Blocked |

Classification is an AI disclosure control, not a separate field-level access-control system. Customer membership controls local record access.

Unstructured ticket extraction has a separate intake gate: a consultant must confirm Internal classification and external disclosure permission, and screening must pass before the extraction call. A saved ticket subsequently requires independent review before AI investigation. Manual entry and structured JSON parsing use no AI.

### Sensitive information

Screening detects common credential assignments, private-key headers, credentials in connection URLs, email addresses and some suspicious instruction/control-character patterns. Findings prevent external AI approval. Detection is heuristic and does not cover every personal identifier or secret format.

The **Review / redact text** action records a revision reason and invalidates relevant approval. It does not provide complete data erasure: older notes, prior records or backups can still contain sensitive information. Users should minimise sensitive data before import.

## 4. Uploaded files and prompt injection

### Implemented controls

| Control | Behaviour |
|---|---|
| File bounds | File-size, extracted-text, signature and archive-expansion checks reject unsupported or excessive inputs |
| Parser isolation | HTTP uploads are parsed in a separate process with a 20-second deadline and a maximum of two concurrent parser jobs |
| Credential handling | The parser does not inherit application credentials or load the application's `.env` file |
| Optional malware scanner | An installed ClamAV executable can scan binary uploads before parsing |
| Security review gate | Unreviewed or rejected documents are excluded from normal AI retrieval |
| Version binding | Security decisions bind to a content/context hash; later content changes invalidate approval |
| AI policy enforcement | Eligibility and screening are checked before indexing/analysis and when selecting AI evidence |
| Restricted model authority | Document text cannot grant application permissions, record approvals or execute proposed commands |
| Response checks | AI responses are schema-validated; recommendations must cite supplied evidence and matching quotations |

Process isolation is not a complete operating-system sandbox: it does not itself deny all filesystem or network access. Production parsing needs a restricted service/container or equivalent platform controls.

Prompt injection cannot be guaranteed to be detected. A malicious document can still influence model interpretation even if its source is correctly cited. Human review, limited model authority and backend access checks remain necessary.

### Malware scanner configuration

```dotenv
# Absolute path to an installed clamscan executable; do not include shell arguments.
ATLAS_CLAMSCAN_PATH=C:/approved/path/to/clamscan.exe
# Block uploads when a scanner is not configured.
ATLAS_REQUIRE_MALWARE_SCAN=1
```

The path is an example, not an installed location. Scanner failure, rejection or timeout blocks the upload. Without configuration, the application reports that scanning was not performed. The company must install the scanner, maintain signatures and monitor its operation. A completed scan is not proof that a file is harmless. Pasted text is handled by content screening, not binary antivirus scanning.

## 5. Approvals attributable to people

Entering a change request's Approval stage creates a Pending decision. An authenticated Approver must record the decision separately.

The ticket creator and current proposal author cannot approve that proposal. Document creators/current content editors cannot independently review their own records. These checks apply on the backend, even if the caller bypasses the interface.

Change decisions record:

- Account ID and display identity.
- Server timestamp, decision and notes.
- Proposal hash and record revision.
- Decision history when subsequent decisions or proposal changes occur.

Changes to the proposal invalidate an Approved decision. Development, deployment and verification transitions require an attributable approval matching the current proposal. Legacy approvals without an actor ID and proposal hash cannot satisfy that requirement.

Source security approval, source evidence validation, change approval and consultant outcome observations are distinct. Marking an outcome checkbox does not replace independent change approval.

## 6. Audit records

Security events cover logins, denied API operations, API reads, account management, review intentions and record-write intentions/completions. They record identifiers and hashes rather than passwords, session tokens or full document bodies. Administrators can inspect the latest 200 events in the app.

The app has no audit edit/delete endpoint. However, database administrators can change the underlying records, and audit writes are not transactional with business writes. For example, a completed business write followed by audit-storage failure can return an error even though the record changed. Production requires a stronger audit delivery and storage design.

## 7. Required company configuration and infrastructure

| Area | What the company must provide or decide | Remaining technical work |
|---|---|---|
| Identity | Approved identity provider, tenant, application registration, employee identifiers, group/role mapping and MFA policy | Implement and validate OIDC/SSO integration; local sign-in is currently implemented |
| Access governance | Who may access each customer; who may review/approve; joiner, mover, leaver and recovery procedures | Provision memberships, operate account lifecycle and periodically review access |
| SAP ingestion | Approved export fields and attachment types; data owner permission; for a connector, SAP endpoint, protocol and read-only service credentials | Direct SAP integration is not implemented; exports can be uploaded now |
| Data classification | Company definitions of Internal, Confidential and Restricted; redaction requirements and retention periods | Align application rules with the approved policy and extend detection where needed |
| External AI | Approved Gemini account/project, permitted data classes, contractual terms, processing location and provider retention requirements | Review the actual provider configuration and authorise external processing; an API key alone is not approval |
| Hosting | Approved host/network, domain, TLS certificates, reverse proxy and production application runtime | Replace/harden the local development server, configure HTTPS and Secure cookies, revise trusted-origin settings |
| Database | Private connectivity, authenticated least-privilege database account, encryption, backup and recovery requirements | Configure MongoDB and demonstrate backup restoration; the app does not provision these controls |
| Secrets | Approved secret store, key owners, rotation and emergency revocation procedures | Integrate managed secrets; local `.env` exclusion from Git is only a development measure |
| File scanning | Installed scanner, updated signatures, service permissions, monitoring and failure policy | Configure the existing ClamAV integration and enable fail-closed scanning |
| Parser sandbox | Restricted filesystem, network and resource policy | Deploy an OS-isolated parser environment; current subprocess isolation is limited |
| Audit/SIEM | Central append-only destination, access policy, retention and alert owners | Implement reliable export/outbox delivery and external tamper-resistant storage |
| Retention/deletion | Rules covering tickets, documents, embeddings, logs, history and backups | Build and validate complete retention/erasure workflows; the redaction editor is not sufficient |
| Security assurance | Threat-model owners, security acceptance criteria, vulnerability response and penetration-test scope | Perform company review and production testing before rollout |

Changing the bind address to expose the current local server is not a production deployment procedure. Authentication is only one part of the required deployment work.

## 8. Verification performed

At implementation completion, 91 automated tests ran: 90 passed and one optional real-MongoDB test was skipped. Tests covered authentication, role/CSRF denial, customer isolation, session expiry/revocation, independent approval, stale approval invalidation, legacy-index exclusion, screening and scanner fail-closed behaviour.

Browser tests covered sign-in, account creation, sign-out, upload/import, local evidence linking and independent security review. They used isolated test accounts and mocked AI. No Gemini requests were consumed. These checks do not establish production security certification or live AI quality.

## 9. Implementation references

- `security.py`: identities, sessions, screening, policy hashes and approval checks.
- `security_http.py`: authenticated routes, administration, review and revision actions.
- `storage.py`: customer scoping, identity attribution and invalidation on edits.
- `uploads.py` / `upload_worker.py`: scanner integration and bounded parser process.
- `server.py`: authenticated HTTP boundary and lifecycle checks.
- `static/security-ui.js`: account, review and administration interface.
- `tests/test_security.py`: security regression coverage.

See also [local security setup](SECURITY.md), [historical documentation](HISTORICAL_DOCUMENTATION.md) and [AI functions](AI_FUNCTIONS.md).
