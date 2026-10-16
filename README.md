# ATLAS Solution Intelligence Engine

A MongoDB-backed investigation workspace with Gemini ticket extraction, semantic retrieval and source-cited recommendations. Starts empty: no seeded tickets, sample knowledge or simulated AI responses.

## Setup

Requires Python 3.10+, MongoDB 8 and a Gemini API key.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # First setup only; preserve an existing .env
```

Edit `.env` locally:

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_REQUESTS_PER_MINUTE=5
GEMINI_REQUESTS_PER_DAY=20
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=atlas_solution_engine
WORKSPACE_CUSTOMER=My Workspace
CONSULTANT_NAME=Consultant
PORT=8000
```

Create a key in [Google AI Studio](https://aistudio.google.com/apikey) and put it after GEMINI_API_KEY=. The file is Git-ignored; credentials remain server-side. Restart after changing configuration. Set the workspace name before creating records: it controls which records are visible.

The defaults are `gemini-3.8-flash` for extraction/recommendations and `gemini-embedding-2` for search. Override `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` or `GEMINI_TIMEOUT_SECONDS` in `.env` if needed. Previous `OPENAI_*` settings are unused; an OpenAI key cannot be used as a Gemini key. Sources indexed with the previous embedding model must be reindexed before retrieval.

Start MongoDB using an existing installation, an Atlas URI, or Docker:

```powershell
docker compose up -d mongodb
.\.venv\Scripts\python.exe server.py
```

Open http://127.0.0.1:8000. On this development machine a portable MongoDB was downloaded into ignored tmp/mongodb/server; scripts/start-local-mongodb.ps1 starts it using data/mongodb. It is an alternative to Docker.

## Use your own data

1. Click **Check AI connection** to test one small live generation request. The dashboard shows the active generation model and ATLAS's locally tracked quota balance. After changing `.env`, restart the Python server; refreshing the browser alone does not reload configuration.
2. In **Knowledge**, upload actual documents or paste text. TXT, MD, JSON, text-based PDF, DOCX, XLSX/XLSM/XLTX and CSV are supported, up to 5 MB. Review application, version and source reference before saving.
3. Sources are saved without AI requests. Use Index / reindex explicitly when approved and ready. Failed indexing retains the document with an error and retry action. AI retrieval searches only Ready sources; local keyword search also searches Pending sources.
4. Create an investigation from actual ticket text or a document. Local parsing uses no AI request. Review and complete the context before saving.
5. Run analysis. Gemini synthesizes recommendations from retrieved chunks. Every recommendation must cite a supplied source and an exact quote; invalid citations reject the response. Insufficient evidence produces diagnostic next steps.
6. Use **Solution workspace** to record requirements, functional/technical proposals, stage owners and verification scenarios without AI. Record evidence, decisions and validated outcomes. Promote outcomes to knowledge by reviewing and saving the draft. Verification requires recorded testing, customer confirmation and deployment evidence.

Ticket and document text used for extraction, embedding and analysis is sent to Gemini. Provider failures are explicit, with no simulated fallback. Changing embedding model requires reindexing.

ATLAS defaults to a local guard of 5 requests per rolling 60 seconds and 20 requests per UTC day. It persists counts in ignored local application data, preflights two-request analysis operations, and prevents ATLAS from exceeding those configured limits. The counter only observes requests made by this ATLAS installation; requests made in AI Studio or other applications can make Gemini reject a call before the local counter reaches zero. A connection check costs one request, ticket extraction costs one, indexing costs one request per batch of up to 16 chunks, and evidence analysis costs two.

## Verification

For the client ITIL CSV structure, dataset replacement, backups and batched indexing, see [Client ticket import](docs/CLIENT_TICKET_IMPORT.md). The importer is explicit; startup never seeds records automatically.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
# Include real MongoDB tests in an isolated temporary database:
$env:RUN_MONGO_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test doubles exist only in tests. Runtime storage and AI always use MongoDB and Gemini. See docs/VALIDATION.md.

## Deployment scope

Functional local, single-workspace application bound to loopback. SSO, roles, document ACLs, live enterprise connectors, background ingestion and production hosting are not implemented. Scope filtering does not replace authentication. Retrieval scores MongoDB-stored vectors in Python; large deployments need a vector index and background jobs. Confidence is heuristic and requires consultant validation.

The former SQLite database is unused and not imported automatically; ignored files are preserved. Uploaded sources begin Unverified. Upload time does not establish the original guidance's freshness.

server.py provides the API and workflow; storage.py handles scoped MongoDB persistence and optimistic concurrency; ai.py calls Gemini; ingestion.py extracts and indexes documents; engine.py retrieves and validates evidence; static/ contains the UI.

For the NTT workflow implementation, review gates and remaining deployment prerequisites, see [NTT workflow](docs/NTT_WORKFLOW.md).
