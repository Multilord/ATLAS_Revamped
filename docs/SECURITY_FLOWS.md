# SAP ingestion and file/prompt-injection controls

These simplified diagrams describe the current local implementation. SAP ingestion uses exports; a live SAP connector is not configured. Malware scanning requires an installed/configured ClamAV scanner.

## 1. SAP ticket ingestion

```mermaid
flowchart TD
    sapExport["SAP ticket export"] --> upload["Authorised user uploads file"]
    upload --> preview["Preview, select fields and redact"]
    preview --> save["Save in permitted customer scope"]
    save --> review["Independent security review"]
    review --> allowed{"Approved Internal content with AI permission?"}
    allowed -->|"No"| localOnly["Local access only"]
    allowed -->|"Yes"| index["Explicit indexing for AI retrieval"]
```

Saving does not contact Gemini. Indexing also requires current approval and passing content screening. Unstructured AI ticket extraction is a separate optional intake action requiring screening and explicit disclosure confirmation.

## 2. File upload and prompt-injection safeguards

```mermaid
flowchart TD
    fileUpload["Uploaded file"] --> fileChecks["File limits and optional malware scan"]
    fileChecks -->|"Rejected"| blocked["Block upload"]
    fileChecks -->|"Accepted"| parsing["Bounded parsing and content screening"]
    parsing --> review["Independent review of text and metadata"]
    review --> eligible{"Approved, unchanged and screening passed?"}
    eligible -->|"No"| restricted["Keep local or redact and re-review"]
    eligible -->|"Yes, with AI permission"| ai["Gemini receives permitted evidence"]
    ai --> validation["Validate response and citations"]
    validation --> consultant["Consultant reviews recommendations"]
```

Malformed files or parser limits can also block an upload. Screening does not guarantee detection of prompt injection. Authorisation remains enforced by application code, and AI output cannot grant approval or execute a fix. Invalid responses/citations are rejected rather than saved as a new valid analysis.
