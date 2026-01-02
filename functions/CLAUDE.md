# Azure Functions - Blob Trigger for Document Ingestion

## Overview

This function (`ingest_document`) triggers when a PDF is uploaded to the `documents` container in Azure Blob Storage. It parses the PDF, extracts metadata, and chunks the content for later storage in Azure SQL Graph.

## Architecture

```
Azure Blob Storage (documents container)
        ↓ (blob trigger)
Azure Function (ingest_document)
        ↓
PDF Parser (PyMuPDF/fitz)
        ↓
Chunker (page-based + size-based)
        ↓
Embeddings (Azure OpenAI text-embedding-3-small)
        ↓
Azure SQL Graph (sources, chunks with JSON embeddings)
        ↓
Concept Extraction (Azure OpenAI GPT-4o-mini) ← PARALLEL: 20 concurrent workers
        ↓
Azure SQL Graph (concepts, edges)
```

**Key Design**: Concept extraction uses parallel processing with 20 concurrent API calls. This reduces processing time from ~18 minutes to ~4.5 minutes for a 400+ chunk book.

## Files

| File | Purpose |
|------|---------|
| `function_app.py` | Main entry point, v2 programming model with decorator |
| `shared/parser.py` | PDF parsing with PyMuPDF, metadata extraction |
| `shared/chunker.py` | Text chunking with page boundaries and overlap |
| `shared/validation.py` | Input validation, cost controls, processing states |
| `shared/logging_utils.py` | Structured JSON logging with timing |
| `shared/storage.py` | Database storage with idempotency (delete-and-replace), JSON embeddings |
| `shared/embeddings.py` | Azure OpenAI text-embedding-3-small for semantic search |
| `shared/concepts.py` | Azure OpenAI GPT-4o-mini for concept extraction (was Claude) |
| `shared/graph.py` | SQL Graph storage with **parallel concept extraction** (ThreadPoolExecutor) |
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
| Max chunks per source | 3000 | `MAX_CHUNKS_PER_SOURCE` | Increased with parallel processing |
| Max chunk size | 4000 chars | `MAX_CHUNK_SIZE` | LLM context efficiency |
| Min text length | 100 chars | `MIN_TEXT_LENGTH` | Catches scanned/empty PDFs |
| Function timeout | 10 min | `host.json` | Consumption plan maximum |
| Max concurrent extractions | 20 | `MAX_CONCURRENT_EXTRACTIONS` | Parallel API calls per document |

### Processing States

```
UPLOADED → PARSING → PARSED → EXTRACTING → COMPLETE
              ↓                    ↓
           PARSE_FAILED      EXTRACT_FAILED
```

Defined in `shared/validation.py` as `ProcessingStatus` enum.

### Validation Pipeline

1. **File size** - Reject files > 100 MB (prevents timeout)
2. **File type** - Check extension is `.pdf`
3. **Magic bytes** - Verify file starts with `%PDF-` (security)
4. **Page count** - Reject documents > 1000 pages (cost control)
5. **Minimum text** - Reject if < 100 chars extracted (catches scanned PDFs)
6. **Chunk count** - Reject if > 500 chunks (cost control)
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

## Parallel Processing

### The Problem

A typical book produces 400+ chunks. Sequential API calls for concept extraction:
- Each call: ~2.5 seconds (Azure OpenAI GPT-4o-mini)
- 426 chunks × 2.5 sec = ~18 minutes
- Azure Functions Consumption plan timeout: 10 minutes maximum

**Result**: Sequential processing causes function timeout for large documents.

### The Solution

Use Python's `ThreadPoolExecutor` to make 20 API calls simultaneously:

```python
# In shared/graph.py
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_CONCURRENT_EXTRACTIONS = 20

def process_source_concepts(source_id: int, chunks: list["Chunk"]) -> dict:
    extractions: dict[int, ExtractionResult] = {}

    def extract_for_chunk(chunk):
        return chunk.id, extract_concepts_from_chunk(chunk.text)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_EXTRACTIONS) as executor:
        future_to_chunk = {
            executor.submit(extract_for_chunk, chunk): chunk
            for chunk in valid_chunks
        }

        for future in as_completed(future_to_chunk):
            chunk_id, extraction = future.result()
            extractions[chunk_id] = extraction
```

### Why 20 Workers?

- Azure OpenAI rate limit: ~1000 requests/minute for this deployment
- 20 concurrent × 2.5 sec/call = ~480 requests/minute (safely under limit)
- More workers → risk rate limiting (429 errors)
- Fewer workers → unnecessarily slow

### Two-Phase Design

1. **Phase 1 (Parallel)**: Extract concepts from all chunks simultaneously using ThreadPoolExecutor
2. **Phase 2 (Sequential)**: Store results to database one at a time (DB operations must be sequential for data integrity)

### Performance

| Document | Chunks | Sequential | Parallel | Speedup |
|----------|--------|------------|----------|---------|
| 287-page textbook | 426 | ~18 min | ~4.5 min | 4x |

### Error Handling

- Each worker has its own try/catch
- Failed extractions are logged but don't stop other workers
- Stats track both successes and errors
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

1. Upload a PDF to `stsecondbrain` → `documents` container
2. Wait 10-60 seconds for trigger
3. Check logs in Azure Portal: Function App → Functions → ingest_document → Monitor
4. Verify output shows: page count, title, author, chunk count

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
