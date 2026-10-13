# Solution Intelligence Engine

A working local prototype for evidence-led enterprise support investigations, based on the supplied 45-page solution brief. Built with Python's standard library, SQLite and browser JavaScript. No package installation, credentials, external APIs or build step required.

## Run

Requires Python 3.10 or later. From this directory:

```powershell
python server.py
```

Open http://127.0.0.1:8000. Use `python server.py --port 8001` if needed. Stop with Ctrl+C. The server binds only to loopback. `npm start` is an optional equivalent if Python is on PATH.

## Try the complete flow

1. Choose **New investigation**, then **Use a sample invoice ticket**, or upload `examples/invoice-ticket.json`.
2. Review the extracted fields and imported chronology. Correct the application and release before creating the investigation.
3. Choose **Find supporting evidence**. Review ranking reasons, source excerpts, conflicting guidance and the legacy ECC version warning.
4. Add observations or test results in **Evidence & Notes**. New evidence invalidates old recommendations; run a fresh search.
5. Select a recommendation for validation. In **Outcome**, record testing, customer confirmation and the final result.
6. Visit **Insights** to see updated counts. Refresh or restart the server to verify persistence.

Try an unrelated printer issue to exercise insufficient evidence. A change request requires approval, development, deployment and verification in addition to testing and customer confirmation before a resolved outcome can be recorded.

## Implemented

- Dashboard, searchable/filterable investigations, knowledge library and local outcome insights.
- Dedicated investigation workspace: Overview, Timeline, Recommendations, Evidence & Notes, Outcome.
- Reviewed TXT/JSON intake with bounded input, timestamp normalization and source references.
- Persisted investigations, chronological evidence, accept/reject decisions, validated outcomes and audit events.
- Keyword retrieval with synonym normalization, exact error matching, application/release compatibility, freshness and recorded validation evidence.
- Confidence categories, explicit abstention and curated conflict indicators. Relevance points are uncalibrated heuristics, never success probabilities.
- Customer filtering in storage reads and retrieval. The demo principal is fixed server-side to Atlas Manufacturing; general sources are reusable. A restricted second-customer fixture is excluded from responses.
- Clear sample-data and disconnected-integration labels. No invented accuracy or time-saving metrics.

## Prototype boundaries

This first slice is an executable development baseline, **not production authentication or AI**. The local server uses one fixed demo principal and is intended for one consultant on one machine. All seeded knowledge is synthetic, including error-code associations and procedures; it is not official SAP advice. The current engine is deterministic lexical retrieval, not embeddings, an LLM or semantic RAG. It does not execute SAP changes or connect to enterprise systems.

Uploads currently support UTF-8 TXT and JSON. For attachments, paste relevant text and the filename into an Attachment note. PDF/Office extraction, binary attachments, live connectors, SSO/RBAC, per-document grants, calibrated hybrid retrieval, grounded model synthesis, robust multi-user concurrency and validated knowledge promotion are planned in `docs/DEVELOPMENT.md`.

The database contains synthetic seed examples alongside user-created investigations. The UI marks seeded records. Counts include both; use a separate development database when evaluating real workflows. No automatic deletion/reset endpoint is provided.

## Storage and tests

SQLite is created at `data/solution-engine.sqlite3` (Git-ignored). Override the path with `SIE_DATABASE`. Tests use isolated temporary databases and never reset your working records.

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests cover tenant filtering, applicability ranking, abstention, imported chronology, malformed inputs, persisted outcomes, audit events, validation gates and HTTP boundaries. They are regression checks over synthetic fixtures, not a retrieval quality benchmark.

## Structure

| Path | Responsibility |
| --- | --- |
| `server.py` | Local HTTP API, scoped SQLite storage, intake and workflow validation |
| `engine.py` | Evidence retrieval, classification, ranking and abstention |
| `seed.py` | Synthetic knowledge and investigation fixtures |
| `static/` | Responsive browser UI, reusable rendering helpers and forms |
| `tests/` | Isolated workflow, retrieval and transport regression tests |
| `docs/` | Requirements interpretation, architecture and next milestones |
