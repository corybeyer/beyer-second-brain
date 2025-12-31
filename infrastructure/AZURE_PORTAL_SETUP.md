# Azure Portal Setup Guide

Step-by-step instructions for setting up Second Brain infrastructure via the Azure Portal.

**Status**: Phase 1 Complete

---

## Prerequisites

- Azure account with an active subscription
- Access to Azure Portal: https://portal.azure.com

---

## Architecture Overview

```
Azure Blob Storage (documents)
        ↓
Azure Function (blob trigger)
        ↓
Azure SQL Database (SQL Graph)
        ↓
Claude API (search/synthesis)
        ↓
Streamlit App (Container Apps)
```

---

## Step 1: Create a Resource Group

1. Go to **Azure Portal** → Search for "Resource groups"
2. Click **+ Create**
3. Fill in:
   - **Subscription**: Select your subscription
   - **Resource group**: `rg-second-brain`
   - **Region**: Choose one (e.g., `Central US`)
4. Click **Review + create** → **Create**

---

## Step 2: Create Storage Account

1. Search for "Storage accounts" → Click **+ Create**
2. **Basics tab**:
   - **Resource group**: `rg-second-brain`
   - **Storage account name**: `stsecondbrain` (must be globally unique)
   - **Region**: Same as resource group
   - **Performance**: Standard
   - **Redundancy**: LRS (Locally-redundant storage)
3. **Advanced tab**:
   - **Require secure transfer**: Enabled
   - **Allow Blob anonymous access**: Disabled
4. Click **Review + create** → **Create**

### Create Container

1. Go to the storage account
2. **Data storage** → **Containers** → **+ Container**
3. Name: `documents`
4. Public access level: **Private**
5. Click **Create**

---

## Step 3: Create Function App

1. Search for "Function App" → Click **+ Create**
2. **Basics tab**:
   - **Resource group**: `rg-second-brain`
   - **Function App name**: `func-secondbrain` (globally unique)
   - **Runtime stack**: Python
   - **Version**: 3.11
   - **Region**: Same as resource group
   - **Operating System**: Linux
   - **Hosting plan**: Consumption (Serverless)
3. **Storage tab**:
   - Use the storage account created above, or create new
4. **Monitoring tab**:
   - Enable Application Insights (recommended)
5. Click **Review + create** → **Create**

---

## Step 4: Create SQL Database

You can either:
- **Option A**: Create a new SQL Server + Database
- **Option B**: Use an existing SQL Server (create just a new database)

### Option A: New SQL Server

1. Search for "SQL databases" → Click **+ Create**
2. **Basics tab**:
   - **Resource group**: `rg-second-brain`
   - **Database name**: `secondbrain`
   - **Server**: Click "Create new"
     - **Server name**: `sql-secondbrain` (globally unique)
     - **Location**: Same region
     - **Authentication**: SQL authentication
     - **Admin login**: `sbadmin`
     - **Password**: Create strong password (save this!)
   - **Want to use SQL elastic pool?**: No
   - **Workload environment**: Development
   - **Compute + storage**: Click "Configure database"
     - Select **Basic** tier (~$5/month)
3. **Networking tab**:
   - **Connectivity method**: Public endpoint
   - **Allow Azure services**: Yes
   - **Add current client IP**: Yes
4. Click **Review + create** → **Create**

### Option B: Existing SQL Server

1. Go to your existing SQL Server
2. Click **+ Create database**
3. Name: `secondbrain`
4. Compute: Basic tier (or share existing compute)

---

## Step 5: Configure Managed Identity

### Enable on Function App (usually auto-enabled)

1. Go to `func-secondbrain`
2. **Settings** → **Identity**
3. **System assigned** tab → Status: **On**
4. Save

### Grant Storage Access

1. Go to `stsecondbrain` (Storage Account)
2. **Access Control (IAM)** → **+ Add role assignment**
3. Role: **Storage Blob Data Contributor**
4. Members: Select "Managed identity" → `func-secondbrain`
5. Click **Review + assign**

### Grant SQL Access

1. Go to your SQL Server
2. **Settings** → **Microsoft Entra ID**
3. Click **Set admin** → Select yourself → Save
4. Go to your database → **Query editor**
5. Login with your Entra credentials
6. Run:

```sql
CREATE USER [func-secondbrain] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [func-secondbrain];
ALTER ROLE db_datawriter ADD MEMBER [func-secondbrain];
```

---

## Step 6: Verify Setup

### Resources Created

| Resource | Name | Location |
|----------|------|----------|
| Resource Group | `rg-second-brain` | Central US |
| Storage Account | `stsecondbrain` | Central US |
| Blob Container | `documents` | - |
| Function App | `func-secondbrain` | Central US |
| SQL Database | `secondbrain` | (your server) |

### Connections

| From | To | Method |
|------|-----|--------|
| Function App | Storage | Managed Identity (Storage Blob Data Contributor) |
| Function App | SQL | Managed Identity (db_datareader, db_datawriter) |

---

## Cost Estimates

| Resource | SKU | Monthly Cost (approx) |
|----------|-----|----------------------|
| Storage Account | Standard LRS | ~$0.50 |
| Function App | Consumption | ~$0.00 (free tier) |
| SQL Database | Basic | ~$5.00 |
| **Total** | | **~$5-6/month** |

---

## Next Steps

1. Create SQL Graph schema (NODE/EDGE tables)
2. Deploy blob trigger function
3. Test document ingestion

See [CLAUDE.md](../CLAUDE.md) for Phase 2 tasks.
