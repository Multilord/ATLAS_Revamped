# ATLAS Solution Intelligence Engine

A MongoDB-backed investigation workspace with OpenAI ticket extraction, semantic retrieval and source-cited recommendations. Starts empty: no seeded tickets, sample knowledge or simulated AI responses.

## Setup

Requires Python 3.10+, MongoDB 8 and an OpenAI API key.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # First setup only; preserve an existing .env
```

Edit `.env` locally:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=atlas_solution_engine
WORKSPACE_CUSTOMER=My Workspace
CONSULTANT_NAME=Consultant
PORT=8000
```

Put your key after OPENAI_API_KEY=. The file is Git-ignored; credentials remain server-side. Restart after changing configuration. Set the workspace name before creating records: it controls which records are visible.

Start MongoDB using an existing installation, an Atlas URI, or Docker:

```powershell
docker compose up -d mongodb
.\.venv\Scripts\python.exe server.py
```

Open http://127.0.0.1:8000. On this development machine a portable MongoDB was downloaded into ignored tmp/mongodb/server; scripts/start-local-mongodb.ps1 starts it using data/mongodb. It is an alternative to Docker.

## Use your own data

1. Click **Check AI connection** to verify credentials and model access. Indexing and analysis exercise paid embeddings and generation.
2. In **Knowledge**, upload actual documents or paste text. TXT, MD, JSON, text-based PDF and DOCX are supported, up to 5 MB. Review application, version and source reference before saving.
3. Sources are stored in MongoDB and embedded. Failed indexing retains the document with an error and retry action. Only Ready sources with the configured embedding model are searched.
4. Create an investigation from actual ticket text or a document. Review AI-extracted context before saving. Manual entry and structured JSON intake also work without a key.
5. Run analysis. OpenAI synthesizes recommendations from retrieved chunks. Every recommendation must cite a supplied source and an exact quote; invalid citations reject the response. Insufficient evidence produces diagnostic next steps.
6. Record evidence, decisions and validated outcomes. Promote outcomes to knowledge by reviewing and saving the draft. Verification requires recorded testing, customer confirmation and deployment evidence.

Ticket and document text used for extraction, embedding and analysis is sent to OpenAI. Responses use store=False. Provider failures are explicit, with no simulated fallback. Changing embedding model requires reindexing.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
# Include real MongoDB tests in an isolated temporary database:
$env:RUN_MONGO_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Test doubles exist only in tests. Runtime storage and AI always use MongoDB and OpenAI. See docs/VALIDATION.md.

## Deployment scope

Functional local, single-workspace application bound to loopback. SSO, roles, document ACLs, live enterprise connectors, background ingestion and production hosting are not implemented. Scope filtering does not replace authentication. Retrieval scores MongoDB-stored vectors in Python; large deployments need a vector index and background jobs. Confidence is heuristic and requires consultant validation.

The former SQLite database is unused and not imported automatically; ignored files are preserved. Uploaded sources begin Unverified. Upload time does not establish the original guidance's freshness.

server.py provides the API and workflow; storage.py handles scoped MongoDB persistence and optimistic concurrency; ai.py calls OpenAI; ingestion.py extracts and indexes documents; engine.py retrieves and validates evidence; static/ contains the UI.
