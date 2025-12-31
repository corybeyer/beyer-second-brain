# Azure Portal Setup Guide

Step-by-step instructions for setting up Second Brain infrastructure via the Azure Portal.

---

## Prerequisites

- Azure account with an active subscription
- Access to Azure Portal: https://portal.azure.com

---

## Step 1: Create a Resource Group

1. Go to **Azure Portal** → Search for "Resource groups"
2. Click **+ Create**
3. Fill in:
   - **Subscription**: Select your subscription
   - **Resource group**: `rg-secondbrain`
   - **Region**: Choose one close to you (e.g., `East US`)
4. Click **Review + create** → **Create**

---

## Step 2: Create Storage Account (for PDFs)

1. Search for "Storage accounts" → Click **+ Create**
2. **Basics tab**:
   - **Resource group**: `rg-secondbrain`
   - **Storage account name**: `secondbrainbooks` (must be globally unique, add numbers if needed)
   - **Region**: Same as resource group
   - **Performance**: Standard
   - **Redundancy**: LRS (Locally-redundant storage)
3. **Advanced tab**:
   - **Require secure transfer**: ✅ Enabled
   - **Allow Blob anonymous access**: ❌ Disabled
4. Click **Review + create** → **Create**
5. Once created, go to the storage account:
   - **Data storage** → **Containers** → **+ Container**
   - Name: `books`
   - Public access level: **Private**
   - Click **Create**

### Get Connection String
1. In your storage account → **Security + networking** → **Access keys**
2. Click **Show** next to key1
3. Copy the **Connection string** - save this for your `.env` file

---

## Step 3: Create PostgreSQL Flexible Server

1. Search for "Azure Database for PostgreSQL flexible servers" → Click **+ Create**
2. **Basics tab**:
   - **Resource group**: `rg-secondbrain`
   - **Server name**: `secondbrain-pg` (add unique suffix if needed)
   - **Region**: Same as resource group
   - **PostgreSQL version**: **16**
   - **Workload type**: **Development** (cheapest option)
   - **Compute + storage**: Click **Configure server**
     - **Compute tier**: Burstable
     - **Compute size**: Standard_B1ms (1 vCore, 2 GB RAM)
     - **Storage**: 32 GB
     - Click **Save**
   - **Authentication method**: PostgreSQL authentication only
   - **Admin username**: `sbadmin`
   - **Password**: Create a strong password (save this!)
3. **Networking tab**:
   - **Connectivity method**: Public access
   - **Allow public access**: ✅ Yes
   - **Firewall rules**:
     - ✅ Add current client IP address
     - ✅ Allow public access from any Azure service
4. Click **Review + create** → **Create**

⏳ This takes 5-10 minutes to deploy.

---

## Step 4: Create the Database

1. Go to your PostgreSQL server
2. **Settings** → **Databases** → **+ Add**
3. Fill in:
   - **Name**: `secondbrain`
   - **Charset**: `UTF8`
   - **Collation**: `en_US.utf8`
4. Click **Save**

---

## Step 5: Enable Extensions (pgvector + AGE)

1. Go to your PostgreSQL server
2. **Settings** → **Server parameters**
3. Search for `azure.extensions`
4. In the value field, select:
   - ✅ `VECTOR`
   - ✅ `AGE`
5. Click **Save**
6. You may need to restart the server:
   - **Overview** → **Restart**

---

## Step 6: Get Connection Details

From your PostgreSQL server **Overview** page, note:
- **Server name**: `<your-server>.postgres.database.azure.com`
- **Admin username**: `sbadmin`
- **Database**: `secondbrain`
- **Port**: `5432`

---

## Step 7: Update Your .env File

Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Fill in your values:

```env
# Azure Storage
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_STORAGE_CONTAINER_NAME=books

# Azure PostgreSQL
POSTGRES_HOST=<your-server>.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DB=secondbrain
POSTGRES_USER=sbadmin
POSTGRES_PASSWORD=<your-password>

# OpenAI (for later phases)
OPENAI_API_KEY=

# Anthropic (optional, for later phases)
ANTHROPIC_API_KEY=
```

---

## Step 8: Test Connectivity

Run the test script:

```bash
python scripts/test_connectivity.py
```

---

## Cost Estimates

| Resource | SKU | Monthly Cost (approx) |
|----------|-----|----------------------|
| Storage Account | Standard LRS | ~$0.02/GB = ~$0.04 |
| PostgreSQL | B1ms Burstable | ~$12-15 |
| **Total** | | **~$15/month** |

💡 **Tip**: Stop the PostgreSQL server when not in use to save costs.

---

## Troubleshooting

### Can't connect to PostgreSQL
1. Check firewall rules include your current IP
2. Verify the server is running (not stopped)
3. Ensure you're using the full server name with `.postgres.database.azure.com`

### Extensions not available
1. Confirm extensions are enabled in Server parameters
2. Restart the server after enabling
3. Connect and run: `CREATE EXTENSION IF NOT EXISTS vector;`

---

## Next Steps

Once connectivity is verified:
1. Run `python scripts/init_db.py` to create tables
2. Proceed to Phase 2: Ingestion Pipeline
