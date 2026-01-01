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
[Future] Azure SQL Graph
```

## Files

| File | Purpose |
|------|---------|
| `function_app.py` | Main entry point, v2 programming model with decorator |
| `shared/parser.py` | PDF parsing with PyMuPDF, metadata extraction |
| `shared/chunker.py` | Text chunking with page boundaries and overlap |
| `shared/validation.py` | Input validation, cost controls, processing states |
| `shared/logging_utils.py` | Structured JSON logging with timing |
| `shared/__init__.py` | Module exports |
| `requirements.txt` | Python dependencies |
| `host.json` | Azure Functions host configuration |

---

## System Behavior Implementation

This function implements patterns from the project's System Behavior spec (see root CLAUDE.md).

### Cost Controls

| Control | Limit | Constant |
|---------|-------|----------|
| Max file size | 100 MB | `MAX_FILE_SIZE_BYTES` |
| Max pages | 1000 | `MAX_PAGES` |
| Max chunks per source | 500 | `MAX_CHUNKS_PER_SOURCE` |
| Max chunk size | 4000 chars | `MAX_CHUNK_SIZE` |
| Min text length | 100 chars | `MIN_TEXT_LENGTH` |

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

### Idempotency (TODO)

When database storage is implemented:
- Check if source with same `file_path` exists
- Strategy: delete-and-replace OR skip if exists
- Wrap operations in transaction for atomicity

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

Per project CLAUDE.md Phase 2:
- [ ] Define SQL Graph schema based on parsed document structure
- [ ] Store sources + chunks in Azure SQL
- [ ] Test end-to-end with sample document
