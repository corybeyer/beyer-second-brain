# Second Brain

A personal knowledge management system for surfacing insights and relationships across a library documents (PDFs, markdown).

## Project Status

**Current Phase**: 4 - Streamlit Application

| Phase | Status |
|-------|--------|
| 1. Infrastructure | ✓ Complete |
| 2. Ingestion Pipeline | ✓ Complete |
| 3. Concept Extraction | ✓ Complete |
| 4. Streamlit App | In Progress |
| 5. Refinement | Future |

See [CLAUDE.md](./CLAUDE.md) for detailed project plan.

## What It Does

1. **Ingest** - Upload PDFs to Azure Blob Storage
2. **Parse** - Blob trigger extracts text and chunks documents
3. **Store** - Chunks saved to Azure SQL with PENDING status
4. **Embed** - Timer function generates embeddings (Azure OpenAI)
5. **Extract** - Timer function extracts concepts (GPT-4o-mini)
6. **Query** - SQL Graph enables relationship discovery
7. **Search** - Claude-powered semantic search and synthesis (Phase 4)

## Architecture

The system uses **two-phase processing** for reliability with large documents:

```
Phase 1: Blob Trigger (fast, always completes)
Documents → Blob Storage → Azure Function → Parse → Chunk → Store (PENDING)

Phase 2: Timer Trigger (self-healing, resumable)
Every 5 min → Check pending work → Embed → Extract Concepts → Mark COMPLETE
```

**Why two phases?** Large documents (800+ pages) would timeout in a single function. The timer function processes chunks in batches across multiple invocations—any size document eventually completes.

## What's Implemented

### Phase 2 (Complete) - Ingestion Pipeline

- **Blob Trigger Function** - Automatically processes uploaded PDFs
- **PDF Parser** - Extracts text, metadata, headings (PyMuPDF)
- **Chunker** - Intelligent splitting with page awareness and overlap
- **Validation** - Size limits (250 MB, 2500 pages, 3000 chunks), magic bytes
- **SQL Graph Schema** - NODE tables (sources, chunks, concepts) + EDGE tables
- **Storage** - Idempotent document storage with transaction safety
- **Logging** - Structured JSON logs with timing metrics

### Phase 3 (Complete) - Concept Extraction & Embeddings

- **Timer Trigger Function** - Runs every 5 min, self-healing/resumable
- **Embeddings** - Azure OpenAI text-embedding-3-small (stored as JSON)
- **Concept Extraction** - GPT-4o-mini extracts concepts from chunks
- **Chunk Status Tracking** - `embedding_status`, `concept_status` for resumability
- **Batch Processing** - 500 embeddings, 200 concepts per timer invocation
- **Early Exit** - If no pending work, exits immediately (minimal cost)
- **Graph Edges** - covers, mentions, related_to relationships

### Database Schema

```
NODE Tables:
├── sources     (documents with status tracking)
├── chunks      (text segments with position)
└── concepts    (extracted topics - Phase 3)

EDGE Tables:
├── from_source (chunk → source)
├── covers      (source → concept)
├── mentions    (chunk → concept)
└── related_to  (concept → concept)
```

## Azure Resources

| Resource | Name | Purpose |
|----------|------|---------|
| Resource Group | `rg-second-brain` | Container for project resources |
| Storage Account | `stsecondbrain` | Document storage (Blob) |
| Function App | `func-secondbrain` | Blob-triggered ingestion |
| SQL Database | `secondbrain` | Chunks + SQL Graph |

## Local Development

```bash
# Install dependencies
pip install -e .

# Set up environment
cp .env.example .env
# Edit .env with your Azure credentials

# Initialize database (requires ODBC driver)
python scripts/init_db.py

# Test connectivity
python scripts/test_connectivity.py
```

## Cost

~$8-11/month for Azure resources:
- Azure SQL Database (Basic): ~$5
- Azure OpenAI (embeddings + GPT-4o-mini): ~$2-5
- Azure Blob Storage: ~$0.50
- Azure Functions (Consumption): ~$0 (free tier)
- Azure Container Apps: ~$0 (free tier)

## License

Private project - not for distribution.
