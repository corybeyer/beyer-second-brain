# Azure Functions - Document Ingestion Pipeline

## What This Does

When you upload a PDF to Azure Blob Storage, this function automatically:
1. Detects the new file
2. Reads and parses the PDF
3. Extracts metadata (title, author, page count)
4. Splits the content into chunks for later processing
5. Logs everything so you can see it worked

---

## The Journey: What We Learned the Hard Way

We spent hours debugging why the function wouldn't trigger. Here's everything that went wrong and why, explained simply.

---

### Lesson 1: There Are Two Ways to Write Azure Functions (v1 vs v2)

**What are v1 and v2?**

Azure Functions can be written two different ways:

**v1 (the old way):** You create a `function.json` file that describes your function, and a separate Python file with the code.
```
functions/
├── ingest_document/
│   ├── __init__.py      # Your code
│   └── function.json    # Configuration file
```

**v2 (the new way):** You use Python decorators in a single file. No `function.json` needed.
```python
# function_app.py
@app.blob_trigger(arg_name="blob", path="documents/{name}", connection="AzureWebJobsStorage")
def ingest_document(blob):
    # Your code here
```

**Our mistake:** We had BOTH. The old `function.json` files AND the new decorator-based code. Azure got confused about which one to use.

**The fix:** Delete the old v1 files. Use only v2.

**But wait, there's more:** Even after cleaning up, the function still wasn't discovered. Why? Because v2 requires a special app setting:

```
AzureWebJobsFeatureFlags = EnableWorkerIndexing
```

Without this setting, Azure doesn't know to look for the decorator-based functions. It just sits there doing nothing.

---

### Lesson 2: Your Code Needs Its Dependencies at Runtime

**The problem:** Our function imports `fitz` (PyMuPDF) to parse PDFs. When we deployed, the function silently failed because `fitz` wasn't installed.

**Why this happens:**

When you deploy via GitHub Actions with a zip file, Azure does NOT automatically run `pip install`. Your code runs directly from the zip file.

**Two valid solutions:**

**Option A: Pre-package dependencies in CI (what we did)**
```yaml
# In GitHub Actions workflow
- name: Install dependencies into package
  run: |
    cd functions
    pip install --target=".python_packages/lib/site-packages" -r requirements.txt
```

Azure Functions automatically looks in `.python_packages/lib/site-packages` for dependencies.

**Option B: Enable remote build (Oryx)**

Set `SCM_DO_BUILD_DURING_DEPLOYMENT=1` in app settings. Azure's Oryx build system will run `pip install -r requirements.txt` during deployment.

**Important:** Remote build only works with certain deployment methods (like zip deploy with the right settings). It does NOT work when `WEBSITE_RUN_FROM_PACKAGE` points directly to a zip URL without build steps.

**How to know if this is your problem:** Run `az functionapp function list` - if it returns empty `[]` but your code is deployed, it's probably a failed import.

---

### Lesson 3: EventGrid vs Polling (Two Ways to Detect New Blobs)

**What's the difference?**

**Polling-based (simpler, higher latency):** Azure Functions periodically scans the blob container for new files. Not real-time - delays can occur, especially under load or during cold starts.

**Event-based / Event Grid (faster, more complex):** Azure Storage sends a notification the instant a file is uploaded. Lower latency, but requires setting up an Event Grid subscription.

**Which plan supports what?**

| Plan | Polling | Event Grid |
|------|---------|------------|
| Consumption (Dynamic) | ✓ Yes | ✓ Yes (recommended) |
| Premium | ✓ Yes | ✓ Yes (recommended) |
| Dedicated | ✓ Yes | ✓ Yes (recommended) |
| **Flex Consumption** | ✗ No | ✓ **Required** |

**Our mistake:** We had this in our code:
```python
@app.blob_trigger(
    ...
    source="EventGrid"  # <-- This was the problem
)
```

This tells Azure "wait for Event Grid notifications" - but we never set up Event Grid! So the function waited forever for notifications that never came.

**The fix:** Remove `source="EventGrid"` to use polling instead:
```python
@app.blob_trigger(
    arg_name="blob",
    path="documents/{name}",
    connection="AzureWebJobsStorage"
    # No source parameter = use polling
)
```

**When should you use Event Grid?**
- If you're on the Flex Consumption plan (required - no polling support)
- If you need lower latency (polling is not real-time)
- If you have high volume (Event Grid is more efficient)
- Microsoft recommends event-based for production workloads

**How to check your plan type:** Look for `Dynamic` in the plan name (e.g., `CentralUSLinuxDynamicPlan`). Dynamic = regular Consumption = polling works.

**A note on polling timing:** You may see "polls every 10 seconds" mentioned online, but this is not guaranteed. Polling-based triggers can be delayed, especially during cold starts or under load. Don't rely on specific timing.

---

### Lesson 4: Managed Identity and Permissions (How Azure Apps Talk to Each Other)

**What is Managed Identity?**

Instead of storing passwords/connection strings, Azure can give your Function App an "identity" - like a user account. Then you grant that identity permission to access other resources.

**Our setup:**
1. Function App (`func-secondbrain`) has a "System-assigned managed identity" enabled
2. That identity was granted roles on the Storage Account (`stsecondbrain`)

**The roles we assigned:**

| Role | What it allows |
|------|----------------|
| `Storage Blob Data Reader` | Read blobs |
| `Storage Blob Data Contributor` | Read, write, delete blobs |

**How to check this:**
1. Go to Storage Account → Access Control (IAM) → Role assignments
2. Look for `func-secondbrain` in the list

**Important:** For blob triggers to work properly, the identity needs at least `Storage Blob Data Contributor`. Some documentation says you need `Storage Blob Data Owner` for blob triggers.

**We also granted SQL access:**
```sql
CREATE USER [func-secondbrain] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [func-secondbrain];
ALTER ROLE db_datawriter ADD MEMBER [func-secondbrain];
```

This lets the function read/write to the SQL database without a password.

---

### Lesson 5: Connection Strings vs Managed Identity (And a Common Gotcha)

**Two ways to connect to storage:**

**Option A: Connection String (what we used)**
```
AzureWebJobsStorage = DefaultEndpointsProtocol=https;AccountName=stsecondbrain;AccountKey=xxx...
```
- Simpler to set up
- Contains a secret (the AccountKey)
- If the key is compromised, someone could access your storage

**Option B: Managed Identity**
```
AzureWebJobsStorage__accountName = stsecondbrain
AzureWebJobsStorage__credential = managedidentity
```
- No secrets stored
- More secure
- Requires RBAC roles to be set up

We used Option A (connection string) because it was already configured when the Function App was created.

**Important gotcha: "Trigger connection" vs "Host storage"**

The `connection` parameter in your blob trigger and the `AzureWebJobsStorage` app setting serve different purposes:

| Setting | Purpose |
|---------|---------|
| `connection="AzureWebJobsStorage"` in trigger | Where the triggered blobs live (the container you're watching) |
| `AzureWebJobsStorage` app setting | Also used by the Functions host for internal state (blob receipts, leases, etc.) |

**What this means:**
- If your blobs are in a different storage account than your host storage, you can set the trigger's `connection` to a different app setting name
- But you ALWAYS need `AzureWebJobsStorage` set for the host to function (it stores receipts in `azure-webjobs-hosts` container)
- In our case, both point to the same storage account (`stsecondbrain`)

---

### Lesson 6: Blob Receipts (Why Your Function Might Skip Files)

**What are blob receipts?**

When the function successfully processes a blob, Azure creates a "receipt" - a record that says "I already processed this file with this ETag."

Next time the function checks, it sees the receipt and skips the file.

**Where are receipts stored?**
In the storage account specified by `AzureWebJobsStorage`, in a container called `azure-webjobs-hosts`, under `blobreceipts/`.

**Our confusion:** After fixing deployment issues, we uploaded a PDF but nothing happened. The logs showed:
```
Blob 'myfile.pdf' will be skipped because this blob has already been processed.
```

The file had been processed by a previous (broken) deployment that failed silently.

**How to reprocess files:**
```bash
# Delete all receipts
az storage blob delete-batch \
  --account-name stsecondbrain \
  --source azure-webjobs-hosts \
  --pattern "blobreceipts/func-secondbrain/*" \
  --auth-mode login

# Restart the function
az functionapp restart --name func-secondbrain --resource-group rg-second-brain
```

Or just upload a new file with a different name.

---

### Lesson 7: Idempotency and Duplicate Processing

**Why this matters:**

Both polling-based and Event Grid triggers can cause your function to run multiple times for the same blob:
- Event Grid can retry on failures
- Polling can pick up the same blob if receipts aren't written yet
- Infrastructure issues can cause duplicate invocations

**Your function should be idempotent** - running it twice on the same file should produce the same result without bad side effects.

**Strategies to handle this:**
1. **Check before processing:** Query your database to see if you already processed this file
2. **Use receipts awareness:** Trust the built-in receipt system for most cases
3. **Move processed files:** Move files to a "processed" container after handling
4. **Use unique constraints:** Let database constraints catch duplicates

**Poison handling:**

If a blob repeatedly fails to process, it can become a "poison" blob. Azure has retry logic:
- Default: 5 retries
- After max retries, the blob is logged as poison

You can customize retry behavior in `host.json`.

---

### Lesson 8: How to Know If Something Is Wrong

**Problem: Function not discovered**
```bash
az functionapp function list --name func-secondbrain --resource-group rg-second-brain -o table
# Returns empty
```

**Possible causes:**
1. Missing `AzureWebJobsFeatureFlags=EnableWorkerIndexing`
2. Import error (missing dependencies)
3. Syntax error in code
4. Mixed v1/v2 files confusing the runtime

**Problem: Function discovered but never triggers**
- Check if `source="EventGrid"` is set without Event Grid configured
- Check if blobs have receipts (already processed)
- Check storage connection (`AzureWebJobsStorage`)
- If on Flex Consumption, you MUST use Event Grid

**Problem: Function triggers but fails**
- Check Application Insights / Monitor tab for error logs
- Common: missing dependencies, permission errors

---

## Required Azure App Settings

These settings MUST be configured in your Function App:

| Setting | Value | Why |
|---------|-------|-----|
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Tells Azure this is a Python function |
| `FUNCTIONS_EXTENSION_VERSION` | `~4` | Which version of the Functions runtime |
| `AzureWebJobsStorage` | Connection string | How to connect to storage for triggers AND host state |
| `AzureWebJobsFeatureFlags` | `EnableWorkerIndexing` | **Required for v2 model to work** |

---

## GitHub Actions Workflow (How Deployment Works)

The workflow at `.github/workflows/main_func-secondbrain.yml`:

1. Triggers on push to `main` when `functions/**` files change
2. Checks out the code
3. **Installs dependencies into `.python_packages/`** (critical!)
4. Logs into Azure using service principal
5. Deploys the entire `functions/` folder

**The critical part:**
```yaml
- name: Install dependencies into package
  run: |
    cd functions
    pip install --target=".python_packages/lib/site-packages" -r requirements.txt
```

Without this (and without remote build enabled), your imports will fail silently.

---

## Debugging Commands Cheat Sheet

```bash
# Is the function discovered?
az functionapp function list --name func-secondbrain --resource-group rg-second-brain -o table

# What are the app settings?
az functionapp config appsettings list --name func-secondbrain --resource-group rg-second-brain -o table

# Restart the function app
az functionapp restart --name func-secondbrain --resource-group rg-second-brain

# Check recent logs
az monitor app-insights query \
  --app func-secondbrain \
  --resource-group rg-second-brain \
  --analytics-query "traces | where timestamp > ago(30m) | order by timestamp desc | take 50"

# Check RBAC on storage
az role assignment list \
  --scope "/subscriptions/YOUR_SUB_ID/resourceGroups/rg-second-brain/providers/Microsoft.Storage/storageAccounts/stsecondbrain" \
  --output table
```

---

## Files in This Folder

| File | What it does |
|------|--------------|
| `function_app.py` | Main entry point with the blob trigger decorator |
| `shared/parser.py` | Parses PDFs using PyMuPDF, extracts text and metadata |
| `shared/chunker.py` | Splits long documents into smaller chunks |
| `requirements.txt` | Python packages needed (azure-functions, pymupdf, etc.) |
| `host.json` | Azure Functions host configuration |
| `local.settings.json.example` | Template for local development settings |

---

## Summary: The 8 Things That Can Go Wrong

1. **Mixed v1/v2 models** → Use only v2, delete old `function.json` files
2. **Missing EnableWorkerIndexing** → Add app setting `AzureWebJobsFeatureFlags=EnableWorkerIndexing`
3. **Dependencies not available** → Pre-package to `.python_packages/` OR enable remote build
4. **EventGrid source without Event Grid** → Remove `source="EventGrid"` or set up Event Grid subscription
5. **Flex Consumption without Event Grid** → Flex requires Event Grid, no polling support
6. **Wrong permissions** → Function identity needs Storage Blob Data Contributor
7. **Blob already processed** → Delete receipts or upload new file
8. **Connection string not set** → Ensure `AzureWebJobsStorage` points to your storage account

If your function isn't working, check these eight things in order.
