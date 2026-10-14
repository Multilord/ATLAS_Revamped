# Validation â€” 14 October 2026

## Quota guard

ATLAS now enforces the configured 5 requests per rolling minute and 20 requests per UTC day before contacting Gemini. Counts persist locally across server restarts. Evidence analysis reserves capacity for its embedding and generation calls before either runs; the connection check uses one generation request. The dashboard displays locally tracked remaining capacity. This counter cannot observe requests made through Google AI Studio or other clients, so upstream quota exhaustion can occur earlier.

## Gemini migration

### Follow-up fix: active configuration and JSON generation

The user selected `gemini-2.5-flash` in `.env`, but the existing server process continued to use `gemini-3.8-flash`. The server was restarted to apply the selected model. The dashboard now displays the active generation model and explains that `.env` changes require a server restart.

Live diagnosis also found HTTP 400 from the provider's constrained decoder: the response schema produced too many decoding states. Generation now requests JSON mode with a compact schema in the system instruction and applies the full Pydantic schema locally before accepting output. Size bounds, required fields, enums, extra-field rejection and source citation validation remain enforced. Gemini 2.5 Flash requests disable optional thinking to reduce generation overhead.

Live ticket extraction passed. A separate live recommendation request passed with one recommendation whose source/chunk IDs and quotation matched the supplied verification evidence. Embeddings also passed. Intermittent HTTP 503 and HTTP 429 were observed during diagnosis; those remain explicit provider availability/quota errors. The connection-check action now tests real JSON generation and embeddings rather than model metadata alone. Failed checks clear the prior Connected display. No verification business records were added to the user's workspace.

All 48 regression tests, including real MongoDB persistence, passed after the final change. Tests cover local bounds/extra-field rejection, the ticket title field, imported timeline limits, live-check failure handling, disabled thinking for Gemini 2.5 Flash, quota enforcement, spreadsheet extraction and the Gemini wire contract. JavaScript syntax and diff checks passed. After restarting the final backend, the user's previously failed ticket upload was retried in the browser and successfully reached Review ticket context with populated fields. The form was left open for user review; no investigation was created by that retry.

### Initial migration results (historical)

The runtime now uses Google's `google-genai` SDK, `GEMINI_API_KEY`, `gemini-3.8-flash` and `gemini-embedding-2`. All 39 automated tests passed, including real MongoDB persistence. SDK transport tests exercise Gemini JSON generation, ticket extraction, separate batched embeddings, response validation, model checks, quota/network errors, busy-provider errors and credential redaction. JavaScript syntax and pip dependency checks passed.

Live checks with the configured key succeeded for both model-access requests and embedding two distinct verification texts into separate 3072-dimensional vectors. Live generation on Gemini 3.8 Flash repeatedly returned HTTP 503 (temporary high demand), so live ticket extraction and recommendation generation remain unverified. The app reports this as temporary provider unavailability with retry guidance. Alternate-model experiments were confined to verification processes; the configured model remains Gemini 3.8 Flash. No workspace business records were added during provider checks. ATLAS was restarted with the Gemini configuration.

## Original audit before the migration

31 automated tests passed, including real MongoDB 8.0.34 persistence. The MongoDB test creates a unique isolated database, checks empty initialization and persistence across clients, then drops only that test database. The application workspace remains empty.

Coverage: customer scope, optimistic concurrency, deduplication, embedding-model isolation, hidden vectors, indexing/retry, quote and citation rejection, abstention, confidence caps, provider failures, intake, chronology, outcome gates, note invalidation, TXT/PDF/DOCX extraction, HTTP origin checks and credential redaction.

OpenAI SDK transport tests validate request schemas and response parsing with an isolated test transport. No API key was provided, so live paid embeddings and generation could not be verified. Add a key to .env, restart, check AI connection, upload a genuine source and analyze a real ticket to verify the account's full path.

Browser checks confirm the empty workspace, MongoDB Connected status, missing-key feedback and knowledge upload form. JavaScript syntax passes. These checks are not a production security audit or retrieval-quality benchmark.
