# Second Brain

A personal knowledge management system for surfacing insights and relationships across a library documents (PDFs, markdown).

## Project Status

**Current Phase**: 3 - Concept Extraction & Graph

| Phase | Status |
|-------|--------|
| 1. Infrastructure | ✓ Complete |
| 2. Ingestion Pipeline | ✓ Complete |
| 3. Concept Extraction | In Progress |
| 4. Streamlit App | Planned |
| 5. Refinement | Future |

See [CLAUDE.md](./CLAUDE.md) for detailed project plan.

## What It Does

1. **Ingest** - Upload PDFs to Azure Blob Storage
2. **Parse** - Azure Function extracts text and chunks documents
3. **Store** - Chunks saved to Azure SQL with graph relationships
4. **Extract** - Claude API identifies concepts from content (Phase 3)
5. **Query** - SQL Graph enables relationship discovery
6. **Search** - Claude-powered semantic search and synthesis (Phase 4)

## Architecture

```
Documents → Blob Storage → Azure Function → Azure SQL Graph → Claude API → Streamlit
                              ↓
                    Parse → Chunk → Store → Extract Concepts
```

## What's Implemented

### Phase 2 (Complete)

- **Blob Trigger Function** - Automatically processes uploaded PDFs
- **PDF Parser** - Extracts text, metadata, headings (PyMuPDF)
- **Chunker** - Intelligent splitting with page awareness and overlap
- **Validation** - Size limits, magic bytes, minimum text checks
- **SQL Graph Schema** - NODE tables (sources, chunks, concepts) + EDGE tables
- **Storage** - Idempotent document storage with transaction safety
- **Logging** - Structured JSON logs with timing metrics

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

~$5-6/month for Azure resources (Basic SQL tier, Consumption Functions, LRS Storage).

## License

Private project - not for distribution.
