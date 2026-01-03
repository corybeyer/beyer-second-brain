# Azure Functions - Document Ingestion & Processing

## Overview

This function app contains two Azure Functions:

1. **`ingest_document`** (Blob Trigger) - Triggers when a PDF is uploaded to the `documents` container. Parses the PDF, extracts metadata, chunks the content, and stores with PENDING status.

2. **`process_pending_chunks`** (Timer Trigger) - Runs every 5 minutes. Processes pending embeddings and concept extraction in batches. Self-healing: if it times out, the next run continues from where it left off.

## Architecture

The function app uses **two-phase processing** for reliability with large documents:

```
PHASE 1: Blob Trigger (fast, always completes)
──────────────────────────────────────────────
Azure Blob Storage (documents container)
        ↓ (blob trigger)
Azure Function (ingest_document)
        ↓
PDF Parser (PyMuPDF/fitz)
        ↓
Chunker (page-based + size-based)
        ↓
Azure SQL Graph (sources, chunks with PENDING status)


PHASE 2: Timer Trigger (self-healing, resumable)
────────────────────────────────────────────────
Azure Function (process_pending_chunks) ← runs every 5 minutes
        ↓
Check for pending work (early exit if none)
        ↓
Embeddings (Azure OpenAI text-embedding-3-small, batch of 500)
        ↓
Concept Extraction (Azure OpenAI GPT-4o-mini, batch of 200)
        ↓
Update chunk status → Mark source COMPLETE when all done
```

**Key Design**: Large documents (800+ pages, 1500+ chunks) would timeout in a single function execution. The timer function processes chunks in batches across multiple invocations—any size document eventually completes.

## Files

| File | Purpose |
|------|---------|
| `function_app.py` | Two functions: `ingest_document` (blob) + `process_pending_chunks` (timer) |
| `shared/parser.py` | PDF parsing with PyMuPDF, metadata extraction |
| `shared/chunker.py` | Text chunking with page boundaries and overlap |
| `shared/validation.py` | Input validation, cost controls, processing states |
| `shared/logging_utils.py` | Structured JSON logging with timing |
| `shared/storage.py` | Database storage, chunk status tracking, batch queries for timer |
| `shared/embeddings.py` | Azure OpenAI text-embedding-3-small for semantic search |
| `shared/concepts.py` | Azure OpenAI GPT-4o-mini for concept extraction |
| `shared/graph.py` | SQL Graph storage (concepts, edges, relationships) |
| `shared/db/connection.py` | SQL database connection with managed identity |
| `shared/__init__.py` | Module exports |
| `requirements.txt` | Python dependencies |
| `host.json` | Azure Functions host configuration (10-minute timeout) |

---

## System Behavior Implementation

This function implements patterns from the project's System Behavior spec (see root CLAUDE.md).

### Cost Controls

| Control | Limit | Constant | Notes |
|---------|-------|----------|-------|
| Max file size | 250 MB | `MAX_FILE_SIZE_BYTES` | Increased for large textbooks |
| Max pages | 2500 | `MAX_PAGES` | Increased for large textbooks |
| Max chunks per source | 3000 | `MAX_CHUNKS_PER_SOURCE` | Increased for timer-based processing |
| Max chunk size | 4000 chars | `MAX_CHUNK_SIZE` | LLM context efficiency |
| Min text length | 100 chars | `MIN_TEXT_LENGTH` | Catches scanned/empty PDFs |
| Function timeout | 10 min | `host.json` | Consumption plan maximum |
| Timer processing cap | 9 min | `MAX_RUNTIME_SECONDS` | Leave 1-min buffer before timeout |
| Embedding batch size | 500 | `get_pending_embedding_chunks()` | Per timer invocation |
| Concept batch size | 200 | `get_pending_concept_chunks()` | Per timer invocation |
| Max extraction retries | 3 | `extraction_attempts < 3` | Before marking chunk FAILED |

### Processing States

**Source-level states** (document lifecycle):
```
UPLOADED → PARSING → PARSED → COMPLETE
              ↓
           PARSE_FAILED
```
Defined in `shared/validation.py` as `ProcessingStatus` enum.

**Chunk-level states** (processing tracking):
```
embedding_status: PENDING → COMPLETE | FAILED
concept_status:   PENDING → EXTRACTED | FAILED
```
- Source moves to COMPLETE when all chunks have `embedding_status=COMPLETE` AND `concept_status=EXTRACTED`
- Chunks track `extraction_attempts` counter (max 3 retries before marking FAILED)
- Timer function queries chunks by status to find pending work

### Validation Pipeline

1. **File size** - Reject files > 250 MB (cost control)
2. **File type** - Check extension is `.pdf`
3. **Magic bytes** - Verify file starts with `%PDF-` (security)
4. **Page count** - Reject documents > 2500 pages (cost control)
5. **Minimum text** - Reject if < 100 chars extracted (catches scanned PDFs)
6. **Chunk count** - Reject if > 3000 chunks (cost control)
7. **Chunk positions** - Verify sequential positions (invariant)
8. **Non-empty chunks** - Ensure at least one chunk created (invariant)

### Structured Logging

**Destination**: Azure Application Insights (configured in `host.json`)

- **Azure Portal**: Function App → Functions → `ingest_document` → Monitor
- **Local dev**: Logs to terminal (stdout) when running `func start`

All logs are JSON-formatted with standard fields:

```json
{
  "timestamp": "2026-01-01T12:00:00Z",
  "level": "INFO",
  "step": "parse",
  "message": "Document parsed successfully",
  "file_path": "documents/data-mesh.pdf",
  "duration_ms": 1523,
  "page_count": 87
}
```

Pipeline steps: `validate`, `read`, `parse`, `chunk`, `store`, `complete`, `error`

**Query example** (Application Insights → Logs):
```kusto
traces
| where timestamp > ago(1h)
| extend parsed = parse_json(message)
| where parsed.step == "parse"
| project timestamp, parsed.file_path, parsed.duration_ms
```

### Idempotency

Implemented in `shared/storage.py` using delete-and-replace pattern:
- Check if source with same `file_path` exists
- Delete existing source (CASCADE removes chunks, edges)
- Insert new source and chunks in single transaction
- All operations wrapped in transaction for atomicity

---

## Embedding Storage

### Why JSON Instead of VECTOR?

Azure SQL has a native `VECTOR(1536)` type for storing embeddings, but it's not available on the Basic tier. Instead, embeddings are stored as JSON strings in `NVARCHAR(MAX)`.

**Storage approach** (in `shared/storage.py`):
```python
# Convert embedding list to JSON string
embedding_json = json.dumps(chunk.embedding) if chunk.embedding else None

# Store in chunks table
cursor.execute(
    """INSERT INTO chunks (..., embedding, ...) VALUES (..., ?, ...)""",
    (..., embedding_json, ...)
)
```

**Retrieval** (for future Streamlit app):
```python
# Load embedding from JSON
embedding = json.loads(row["embedding"]) if row["embedding"] else None
```

**Trade-offs**:
- ❌ No native `VECTOR_DISTANCE()` function for similarity search
- ❌ Larger storage size (JSON overhead)
- ✅ Works on Basic tier ($5/month)
- ✅ Can migrate to VECTOR type later if needed
- ✅ Easy to debug (human-readable)

**Future migration**: If Azure SQL VECTOR functions become available on Basic tier, run:
```sql
ALTER TABLE chunks ALTER COLUMN embedding VECTOR(1536);
-- Then update Python code to use VECTOR casting
```

---

## Database Schema Migration

The timer function requires chunk-level status tracking columns. If your database was created before the two-phase architecture, run the migration.

### Required Columns

| Column | Type | Purpose |
|--------|------|---------|
| `embedding_status` | NVARCHAR(20) | PENDING, COMPLETE, FAILED |
| `concept_status` | NVARCHAR(20) | PENDING, EXTRACTED, FAILED |
| `extraction_attempts` | INT | Retry counter (max 3) |
| `extraction_error` | NVARCHAR(500) | Last error message |

### Migration Options

**Option 1: Use init_db.py** (recommended for local dev):
```bash
python scripts/init_db.py --migrate
```

**Option 2: Manual SQL** (Azure Portal → Query editor):
```sql
-- Add columns for retry tracking
ALTER TABLE chunks ADD extraction_attempts INT NOT NULL DEFAULT 0;
ALTER TABLE chunks ADD extraction_error NVARCHAR(500) NULL;

-- Add indexes for timer function queries
CREATE INDEX IX_chunks_embedding_status ON chunks(embedding_status);
CREATE INDEX IX_chunks_concept_status ON chunks(concept_status);
```

**Option 3: Fix existing data** (if concepts already extracted):
```sql
-- Mark already-processed chunks as complete
UPDATE chunks SET concept_status = 'EXTRACTED' WHERE concept_status = 'PENDING';
UPDATE sources SET status = 'COMPLETE' WHERE status = 'PARSED';
```

### Symptom of Missing Columns

Timer function fails with:
```
Invalid column name 'extraction_attempts'
```

This means the migration hasn't been run. Add the columns and the timer will resume.

---

## Timer-Based Processing (Self-Healing)

### The Problem

A typical book produces 400+ chunks. An 850-page textbook generates 1787 chunks. Even with parallel processing:
- Azure Functions Consumption plan timeout: 10 minutes maximum
- Large documents cannot complete in a single function execution

**Result**: Single-function processing times out for very large documents.

### The Solution: Two-Phase Architecture

Decouple heavy processing from the blob trigger:

1. **Blob Trigger** (`ingest_document`): Fast path that always completes
   - Parse PDF, chunk content, store with PENDING status
   - No API calls, no timeouts for large files

2. **Timer Trigger** (`process_pending_chunks`): Self-healing, resumable
   - Runs every 5 minutes
   - Processes chunks in batches (500 embeddings, 200 concepts)
   - Exits early if no pending work (minimal cost)
   - If it times out, next run continues from checkpoint

```python
# In function_app.py
@app.timer_trigger(schedule="0 */5 * * * *", arg_name="timer")
def process_pending_chunks(timer: func.TimerRequest) -> None:
    # 1. Early exit if no work
    stats = get_processing_stats()
    if stats["pending_embeddings"] == 0 and stats["pending_concepts"] == 0:
        return  # Exit immediately, minimal cost

    # 2. Process embeddings batch (500 chunks)
    for chunk in get_pending_embedding_chunks(limit=500):
        embedding = get_embedding(chunk["text"])
        update_chunk_embedding(chunk["id"], embedding)

    # 3. Process concept extraction batch (200 chunks)
    for chunk in get_pending_concept_chunks(limit=200):
        extraction = extract_concepts_from_chunk(chunk["text"])
        store_chunk_extraction_standalone(...)
        update_chunk_concept_status(chunk["id"], "EXTRACTED")

    # 4. Check if any sources are now complete
    for source_id in processed_source_ids:
        if check_source_complete(source_id):
            update_source_status(source_id, "COMPLETE")
```

### Why This Approach?

- **Self-healing**: If timer times out (9-min cap), next run continues from checkpoint
- **No size limit**: 1787 chunks? Just takes 4-5 timer invocations
- **Low idle cost**: Early exit when nothing to process (~100ms check)
- **Simpler blob trigger**: Parse/chunk/store only, always completes

### Batch Sizes

| Operation | Batch Size | Rationale |
|-----------|------------|-----------|
| Embeddings | 500 | Fast (~0.3s each), can process many per run |
| Concept Extraction | 200 | Slower (~2s each), process fewer to stay under timeout |

### Performance

| Document | Chunks | Timer Invocations | Total Time |
|----------|--------|-------------------|------------|
| 287-page book | 426 | ~2 | ~10 min |
| 850-page book | 1787 | ~5 | ~25 min |

### Error Handling

- Failed chunks marked with `FAILED` status and `extraction_error` message
- `extraction_attempts` counter tracks retries (max 3)
- Failures don't stop other chunks from processing
- Progress logged every 50 chunks

---

## Deployment

### Required Azure App Settings

These must be configured in `func-secondbrain` → Environment variables:

| Setting | Value | Purpose |
|---------|-------|---------|
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Runtime |
| `FUNCTIONS_EXTENSION_VERSION` | `~4` | Functions runtime version |
| `AzureWebJobsStorage` | Connection string to storage account | Blob trigger connection |
| `AzureWebJobsFeatureFlags` | `EnableWorkerIndexing` | **Required for v2 programming model** |
| `AZURE_OPENAI_ENDPOINT` | Azure AI Foundry endpoint URL | For embeddings and concept extraction |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-small` | Deployment name for embeddings |
| `AZURE_OPENAI_COMPLETION_DEPLOYMENT` | `gpt-4o-mini` | Deployment name for concept extraction |
| `SQL_SERVER` | Your SQL server FQDN | Database connection |
| `SQL_DATABASE` | `secondbrain` | Database name |

**Note**: Azure OpenAI uses managed identity authentication (DefaultAzureCredential). No API keys needed if Function App has "Cognitive Services OpenAI User" role on the Azure OpenAI resource.

### GitHub Actions Workflow

The workflow (`.github/workflows/main_func-secondbrain.yml`) deploys on push to `main` when `functions/**` changes.

**Critical: Dependencies must be packaged with the deployment.**

```yaml
- name: Install dependencies into package
  run: |
    cd functions
    pip install --target=".python_packages/lib/site-packages" -r requirements.txt
```

Azure Functions Python runtime looks for dependencies in `.python_packages/lib/site-packages`.

---

## Lessons Learned (Troubleshooting Guide)

### Issue 1: Function Not Discovered (Empty function list)

**Symptom**: `az functionapp function list` returns `[]`

**Root Causes & Solutions**:

1. **Missing `AzureWebJobsFeatureFlags`**
   - v2 programming model (decorator-based) requires `EnableWorkerIndexing`
   - Without it, runtime looks for `function.json` files (v1 model)
   - Fix: Add app setting `AzureWebJobsFeatureFlags=EnableWorkerIndexing`

2. **Dependencies not deployed**
   - If `import fitz` fails, function discovery silently fails
   - `WEBSITE_RUN_FROM_PACKAGE` runs directly from zip without building
   - Fix: Install dependencies into `.python_packages/lib/site-packages` in workflow

3. **Mixed v1/v2 programming models**
   - Having both `function_app.py` and `function.json` causes confusion
   - Fix: Use only v2 model (delete `function.json` files)

### Issue 2: Blob Trigger Not Firing

**Symptom**: Function discovered but doesn't execute on blob upload

**Root Causes & Solutions**:

1. **EventGrid source without Event Grid configured**
   - `source="EventGrid"` in decorator requires Event Grid subscription
   - Regular Consumption plan supports polling mode (no Event Grid needed)
   - Fix: Remove `source="EventGrid"` parameter from decorator

2. **Wrong hosting plan**
   - Flex Consumption: Requires Event Grid (no polling)
   - Regular Consumption (Dynamic): Supports polling (simpler)
   - Check: Look for `CentralUSLinuxDynamicPlan` (Dynamic = regular Consumption)

3. **Storage connection not configured**
   - `AzureWebJobsStorage` must point to the storage account with the blob container
   - Can use connection string or managed identity

### Issue 3: Blobs Already Processed (Skipped)

**Symptom**: Logs show "blob will be skipped...already been processed"

**Cause**: Blob receipts exist from previous runs

**Solutions**:
- Upload a NEW file (different name or content)
- Or delete receipts: `az storage blob delete-batch --source azure-webjobs-hosts --pattern "blobreceipts/*"`

---

## Debugging Commands

### Check if function is discovered
```bash
az functionapp function list \
  --name func-secondbrain \
  --resource-group rg-second-brain \
  -o table
```

### Check app settings
```bash
az functionapp config appsettings list \
  --name func-secondbrain \
  --resource-group rg-second-brain \
  -o table
```

### Check host status
```bash
az rest --method get \
  --url "https://func-secondbrain.azurewebsites.net/admin/host/status" \
  --headers "x-functions-key=$(az functionapp keys list --name func-secondbrain --resource-group rg-second-brain --query masterKey -o tsv)"
```

### View logs (Application Insights)
```bash
az monitor app-insights query \
  --app func-secondbrain \
  --resource-group rg-second-brain \
  --analytics-query "traces | where timestamp > ago(30m) | order by timestamp desc | take 50"
```

### Restart function app
```bash
az functionapp restart \
  --name func-secondbrain \
  --resource-group rg-second-brain
```

---

## Key Insights

### Python v2 Programming Model

```python
# Correct v2 blob trigger (no EventGrid for Consumption plan)
@app.blob_trigger(
    arg_name="blob",
    path="documents/{name}",
    connection="AzureWebJobsStorage"
)
def ingest_document(blob: func.InputStream) -> None:
    ...
```

### Azure OpenAI with Managed Identity

Both embeddings and concept extraction use Azure OpenAI with managed identity (no API keys):

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)
client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-02-01",
)
```

### Dependency Packaging

Azure Functions Python does NOT auto-install from `requirements.txt` when using `WEBSITE_RUN_FROM_PACKAGE`. Dependencies must be:

1. Pre-installed into `.python_packages/lib/site-packages` in the deployment package
2. OR use `SCM_DO_BUILD_DURING_DEPLOYMENT=true` with SCM deployment (not zip deployment)

### Blob Trigger Polling

On Consumption plan, blob trigger uses polling:
- Polls every 10 seconds when active
- May take up to 10 minutes on cold start
- Uses blob receipts to track processed files (prevents re-processing)

---

## What NOT to Do

1. **Don't mix v1 and v2 models** - Choose one, delete the other
2. **Don't use `source="EventGrid"` without Event Grid setup** - Causes silent failure
3. **Don't assume remote build works with zip deployment** - It doesn't
4. **Don't forget `EnableWorkerIndexing`** - v2 model won't work without it
5. **Don't commit secrets** - Use app settings, not hardcoded values

---

## Testing

### Blob Trigger (ingest_document)
1. Upload a PDF to `stsecondbrain` → `documents` container
2. Wait 10-60 seconds for trigger
3. Check logs in Azure Portal: Function App → Functions → ingest_document → Monitor
4. Verify output shows: page count, title, author, chunk count
5. Check database: source created with status=PARSED, chunks have embedding_status=PENDING

### Timer Trigger (process_pending_chunks)
1. Wait up to 5 minutes for next timer invocation
2. Check logs in Azure Portal: Function App → Functions → process_pending_chunks → Monitor
3. Verify output shows: embeddings_processed, concepts_processed, sources_completed
4. Check database: chunks should have embedding_status=COMPLETE, concept_status=EXTRACTED
5. Source should have status=COMPLETE when all chunks are done

---

## Next Steps

Per project CLAUDE.md Phase 4 (Streamlit Application):
- [ ] Set up Streamlit app structure (MVC pattern)
- [ ] Implement semantic search interface with VECTOR_DISTANCE queries
- [ ] Build concept explorer (list concepts, browse relationships)
- [ ] Create source comparison view (side-by-side concept coverage)
- [ ] Add RAG-powered Q&A (retrieve chunks, synthesize with Claude)
- [ ] Deploy to Azure Container Apps

Phase 2 (Ingestion Pipeline) and Phase 3 (Concept Extraction) are complete.
