# Client ITIL ticket import

The CSV importer reads the supplied ticket structure without using AI to infer missing fields. Run a preview first:

```powershell
.\.venv\Scripts\python.exe scripts\seed_tickets.py path\to\tickets.csv
```

To replace the previous seed dataset:

```powershell
.\.venv\Scripts\python.exe scripts\seed_tickets.py path\to\tickets.csv --apply
```

This backs up affected records to ignored `data/backups/`, imports investigations and knowledge sources, verifies replacement IDs, and removes previous `SYN-H` / `SYN-Q` seeds, including manually created investigations referencing those ticket IDs. Other records are retained. Original CSV rows remain attached to each imported record for reconciliation. Client datasets are not included in source control.

The supplied dates use month/day/year. Individual stage timestamps are absent, so the timeline labels imported stages as undated. Ticket types are normalized to the application's Incident, Service request and Change request values. Closed workaround-only tickets map to Workaround; unverified closures map to Closed - other. The supplied resolution quality is retained. Test/approval/deployment/customer-confirmation flags are not inferred from closure alone.

The ITIL workflow tab shows clarification, investigation, functional solutioning, technical solutioning, change stages, verification, root cause, sources and lifecycle. New intake captures customer, platform, module, component, scenario and clarification. A single-ticket JSON export accepts the client's column names. Evidence & Notes supports acceptance, acknowledgment, clarification, investigation, solutioning, approval, development, deployment and verification entries. Resolution gates still apply to new consultant-recorded outcomes.

Knowledge sources include the full historical context. Shared-generalized rows use General scope; customer-only sources remain customer scoped. Imported sources start Reviewed or Unverified rather than automatically receiving the application's Verified badge. Workaround and unverified sources receive lower retrieval scores; unverified sources are capped at Low confidence. External source references are preserved without claiming the linked pages were checked.

Embedding sends the historical ticket text to the configured Google Gemini API. After approval for that transfer, resume indexing without replacing records:

```powershell
.\.venv\Scripts\python.exe scripts\seed_tickets.py path\to\tickets.csv --index-only
```

Indexing uses batches of up to 16 chunks and respects local minute/day limits. Unindexed sources remain Pending and are excluded from AI retrieval. The current 50-ticket import has 57 chunks, requiring four embedding requests. No live recommendation quality claim is made until indexing and generation are verified.
