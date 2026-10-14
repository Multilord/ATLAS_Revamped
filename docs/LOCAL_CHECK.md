# Local verification - 14 October 2026

Historical audit before the Gemini migration. The current runtime uses Gemini and `GEMINI_API_KEY`; the OpenAI details below describe the version checked at the time. See VALIDATION.md for migration checks.

Verdict: the local application and MongoDB workflow work in the checks below. Full live AI functionality is blocked by an empty OPENAI_API_KEY; it has not been verified against OpenAI. This is a local single-workspace application, not a complete enterprise deployment.

## Version and recovered context

- Local main: c01b6d8758ca601c49804ec90383a442cb6db255.
- GitHub origin HEAD returned the same commit via git ls-remote.
- Previous chat found in the archive: Start development (01a1351e-b3c7-7470-be3c-64b32e82914f).
- Application and MongoDB were stopped when this check began. Both were started for verification and left running at http://127.0.0.1:8000.

## Checks completed

- All 31 existing automated tests passed with RUN_MONGO_TESTS=1, including real MongoDB persistence. AI success-path tests use isolated test doubles or an SDK mock transport, not live OpenAI.
- JavaScript syntax check passed; pip check found no broken requirements.
- Additional real HTTP/MongoDB smoke verification passed: text extraction, source storage, explicit missing-key indexing failure, retry, duplicate rejection, source review gates, structured JSON intake, investigation creation, explicit missing-key analysis failure, evidence notes, resolution gates, recorded outcome and persistence through a new database client.
- The additional smoke check used a unique atlas_test_audit_* database, removed only that disposable database afterward, and left application records untouched. Its script is in ignored tmp/verify_live_workflow.py.
- Browser verified Dashboard, Investigations, Knowledge and Insights, knowledge upload form, manual intake form and actionable missing-key feedback. No browser console errors were captured.
- Running health endpoint: MongoDB Connected; AI API key missing.
- Application workspace remains empty: zero investigations and zero sources. No synthetic business records were inserted into it.

## Remaining blockers and scope

Set OPENAI_API_KEY privately in .env and restart the app. Then check the AI connection, upload a genuine source, confirm indexing reaches Ready, extract a genuine ticket and run analysis to verify citations. Model-access checks alone do not verify embeddings or generation. Live AI accuracy and retrieval quality remain unmeasured.

Authentication/SSO, roles, document ACLs, live SAP/SharePoint/Confluence connectors, background ingestion, OCR, production hosting and indexed vector search are not implemented. Current SharePoint/Confluence support accepts uploaded exports. See DEVELOPMENT.md for remaining scope.

No application source code was changed by this audit. This report is the only new tracked-path file.
