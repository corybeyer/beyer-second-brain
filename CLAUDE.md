# Second Brain: Data Leadership Knowledge System

## Objective

Build a personal knowledge system that ingests documents (PDFs, markdown) on data team management, enables semantic search across the content, and surfaces relationships between concepts across different authors and sources.

**Core question we want to answer**: "What do my sources collectively say about topic X, and how do different authors' perspectives relate?"

---

## Architecture Overview

```
Azure Blob Storage (PDFs, Markdown)
        ↓
   Azure Function (Blob Trigger)
        ↓
   PDF Parser / MD Reader + Chunker
        ↓
   ┌────┴────┐
   ↓         ↓
Chunks      Concept Extraction (Claude API)
   ↓         ↓
   └────┬────┘
        ↓
   Azure SQL Database
   ├── Tables (sources, chunks)
   └── SQL Graph (concepts, relationships)
        ↓
   Claude API (semantic search + synthesis)
        ↓
   Streamlit App (Azure Container Apps)
```

### Ingestion Workflow

```
1. UPLOAD      → PDF/MD lands in Azure Blob Storage
2. TRIGGER     → Azure Function (Blob Trigger) fires
3. PARSE       → Extract text from PDF (PyMuPDF) or read Markdown
4. CHUNK       → Split into sections (by heading, chapter, or sliding window)
5. STORE       → Insert source + chunks into Azure SQL
6. EXTRACT     → Claude extracts concepts from each chunk
7. BUILD GRAPH → Create nodes and edges in SQL Graph
8. DONE        → Content searchable via app
```

---

## System Behavior

This section defines how the system behaves under real conditions—failure modes, recovery patterns, and operational constraints.

### Failure Modes

| Step | Failure | Impact | Handling |
|------|---------|--------|----------|
| Blob Trigger | Function timeout (10 min max) | Large PDF unprocessed | Enforce size limits, log and skip |
| PDF Parse | Corrupt/encrypted/scanned file | Ingestion fails | Mark source as `failed`, log reason |
| Chunking | Text too sparse or malformed | Poor chunk quality | Validate minimum text length |
| Claude API | Rate limit (429) or timeout | Concepts not extracted | Retry with exponential backoff |
| Claude API | Context too large | Chunk rejected | Split oversized chunks before sending |
| SQL Write | Connection drop mid-transaction | Partial data | Wrap in transaction, rollback on failure |
| SQL Write | Duplicate key | Re-processing conflict | Use upsert patterns (MERGE) |

### Processing States

Track document lifecycle to enable recovery and prevent duplicate work:

```
UPLOADED → PARSING → PARSED → EXTRACTING → COMPLETE
              ↓                    ↓
           PARSE_FAILED      EXTRACT_FAILED
```

- Add `status` and `error_message` columns to sources table
- Query by status to find stuck/failed documents
- Enable manual retry of failed documents

### Idempotency

Same input must produce same result. Critical for retries and reprocessing:

| Entity | Natural Key | Strategy |
|--------|-------------|----------|
| Source | `file_path` | Skip if exists, or delete-and-replace |
| Chunk | `source_id` + `position` | Delete all chunks for source, re-insert |
| Concept | `name` (case-insensitive) | Upsert (MERGE on name) |
| Edges | `$from_id` + `$to_id` | Upsert or recreate with source |

### Retry Patterns

| Operation | Strategy | Max Retries | Backoff | Notes |
|-----------|----------|-------------|---------|-------|
| Claude API | Exponential | 3 | 2s, 4s, 8s | Respect `Retry-After` header |
| SQL Connection | Exponential | 3 | 1s, 2s, 4s | Use connection pooling |
| SQL Transaction | None | 0 | - | Fail fast, log for manual review |
| Blob Read | Automatic | - | - | Azure handles trigger retries |

### Cost Controls

| Control | Limit | Rationale |
|---------|-------|-----------|
| Max PDF size | 100 MB | Function memory (1.5 GB) and timeout |
| Max pages per PDF | 1000 | Reasonable book length |
| Max chunks per source | 500 | Claude API cost per document |
| Max chunk size | 4000 chars | Claude context efficiency |
| Daily Claude API budget | $25 | Alert threshold, not hard stop |
| Max concurrent extractions | 5 | Rate limit protection |

### Observability

**Logging** (structured JSON):
```json
{
  "timestamp": "2025-01-01T12:00:00Z",
  "level": "INFO",
  "step": "parse",
  "source_id": 42,
  "file_path": "documents/data-mesh.pdf",
  "duration_ms": 1523,
  "chunks_created": 87
}
```

**Key Metrics**:
- Documents processed (success/failure by type)
- Chunks created per source (avg, p95)
- Concepts extracted per source
- Claude API latency and token usage
- Processing queue depth (pending sources)

**Alerts** (future):
- Function failure rate > 10%
- Claude API error rate > 5%
- Processing stuck (no progress in 1 hour)
- Daily cost approaching budget

### Invariants

These must always be true. Violations indicate bugs:

1. Every chunk belongs to exactly one source (`source_id` FK)
2. Every source has a valid `status` (enum, not null)
3. Concept names are unique (case-insensitive, enforced by unique index)
4. No orphaned chunks (cascade delete when source deleted)
5. No orphaned edges (cascade delete when node deleted)
6. Chunk positions are sequential within a source (1, 2, 3...)
7. Sources with `status = 'COMPLETE'` have at least one chunk

### Boundaries & Contracts

**Function Input Contract**:
- Blob must be PDF or Markdown (validate by extension and magic bytes)
- File size ≤ 100 MB
- File path format: `documents/{filename}.{pdf|md}`

**Function Output Contract**:
- On success: source created with `status = 'PARSED'`, chunks inserted
- On failure: source created with `status = 'PARSE_FAILED'`, `error_message` set
- Idempotent: re-triggering same blob produces same end state

**Claude API Contract**:
- Input: chunk text ≤ 4000 chars
- Output: JSON with `concepts` array, each with `name`, `description`, `category`
- Timeout: 30 seconds per chunk

---

## File Structure (Option A: Split by Workload)

```
second-brain/
├── CLAUDE.md              # This file - project context
├── README.md
├── pyproject.toml
├── .env.example
│
├── .claude/
│   ├── commands/          # Custom slash commands
│   │   ├── judge.md       # /project:judge - code review
│   │   ├── security.md    # /project:security - security check
│   │   ├── git-state.md   # /project:git-state - git status
│   │   └── phase-status.md
│   └── settings.json      # Permissions and hooks
│
├── functions/             # AZURE FUNCTIONS (blob triggers)
│   ├── ingest_document/   # Triggered on blob upload
│   │   ├── __init__.py
│   │   └── function.json
│   ├── shared/            # Shared code for functions
│   │   ├── parser.py      # PDF/MD parsing
│   │   ├── chunker.py     # Text chunking
│   │   └── concepts.py    # Claude concept extraction
│   ├── host.json
│   └── requirements.txt
│
├── app/                   # INTERACTIVE APP (MVC pattern)
│   ├── models/            # Data classes, view models
│   ├── views/             # Streamlit pages, UI components
│   └── controllers/       # Search logic, orchestration
│
├── shared/                # COMMON CODE (used by functions and app)
│   ├── db/                # Database connection, schema
│   │   ├── connection.py
│   │   └── models.py
│   └── config.py          # Environment, settings
│
├── scripts/               # One-off utilities, CLI tools
│   ├── init_db.py
│   └── test_connectivity.py
│
├── infrastructure/        # Azure setup
│   ├── main.bicep
│   ├── deploy.sh
│   └── AZURE_PORTAL_SETUP.md
│
└── tests/
```

### Folder Rules

| Folder | Contains | Pattern |
|--------|----------|---------|
| `functions/` | Azure Functions for document ingestion | Blob-triggered processing |
| `app/` | Streamlit UI, user-facing features | MVC (models/views/controllers) |
| `shared/` | Database, config, utilities | Used by both functions and app |
| `scripts/` | One-off tools, setup scripts | CLI utilities |
| `infrastructure/` | Azure IaC, setup guides | DevOps |

---

## Project Phases

### Phase 1: Infrastructure ✓ COMPLETE
- [x] Project structure and CLAUDE.md
- [x] Slash commands for workflow (/judge, /security, /git-state)
- [x] Azure Resource Group (`rg-second-brain`)
- [x] Azure Blob Storage account (`stsecondbrain`) + `documents` container
- [x] Azure SQL Database (`secondbrain` on existing server)
- [x] Azure Function App (`func-secondbrain`, Consumption plan)
- [x] Managed identity: Function → Storage (Storage Blob Data Contributor)
- [x] Managed identity: Function → SQL (db_datareader, db_datawriter)

### Phase 2: Ingestion Pipeline (Azure Function) ✓ COMPLETE
- [x] Align codebase with Azure SQL architecture (remove PostgreSQL code)
- [x] Blob trigger function scaffold
- [x] PDF text extraction (PyMuPDF)
- [x] Chunking strategy (page-based + size-based with overlap)
- [x] SQL Graph schema (sources, chunks, concepts as NODE; edges for relationships)
- [x] Database storage with idempotency (delete-and-replace pattern)
- [x] Graph edges (from_source) linking chunks to sources

### Phase 3: Concept Extraction & Graph ✓ COMPLETE
- [x] Claude API integration for concept extraction
- [x] Concept extraction prompt design
- [x] OpenAI embeddings for semantic search
- [x] Upsert concepts to SQL Graph nodes
- [x] Build edges (covers, mentions, related_to)
- [x] Background scripts (cross-source pass, embedding similarity)

### Phase 4: Streamlit Application ← CURRENT
- [ ] Search interface (Claude-powered semantic search)
- [ ] Concept explorer (graph visualization)
- [ ] Source comparison view
- [ ] Deploy to Azure Container Apps

### Phase 5: Refinement (Future)
- [ ] Highlight extraction if feasible
- [ ] Citation/quote extraction
- [ ] Reading notes integration
- [ ] Chat interface over knowledge base

---

## Current Phase: 4 - Streamlit Application

### Detailed Tasks
1. Set up Streamlit app structure (MVC pattern)
2. Implement semantic search interface with VECTOR_DISTANCE queries
3. Build concept explorer (list concepts, browse relationships)
4. Create source comparison view (side-by-side concept coverage)
5. Add RAG-powered Q&A (retrieve chunks, synthesize with Claude)
6. Deploy to Azure Container Apps

**Approach**: Build incrementally - search first, then exploration features.

### Azure Resources (Phase 1 Complete)

| Resource | Name | Location |
|----------|------|----------|
| Resource Group | `rg-second-brain` | Central US |
| Storage Account | `stsecondbrain` | Central US |
| Blob Container | `documents` | - |
| Function App | `func-secondbrain` | Central US |
| SQL Database | `secondbrain` | Existing server (different RG) |

### Decisions Made
- **Azure SQL over PostgreSQL**: SQL Graph provides native graph capabilities; no need for Apache AGE workarounds
- **Claude API for search**: Using Claude for semantic search and synthesis instead of vector embeddings (pgvector)
- **Azure Functions for ingestion**: Blob trigger automatically processes new documents
- **Generic sources schema**: Supports PDFs, markdown, and future document types via `source_type` field
- **Option A folder structure**: Separated `functions/` (ingestion) from `app/` (interactive) with `shared/` for common code
- **MVC for app**: The Streamlit app will follow models/views/controllers pattern
- **Managed identity for auth**: No connection strings with passwords; Function App uses system-assigned managed identity
- **Reuse existing SQL server**: Database created on existing SQL server in separate resource group
- **Defer schema until after parsing**: Parse documents first to understand data structure, then design schema

### Architecture Rationale
- **Why not PostgreSQL?** Azure PostgreSQL doesn't support Apache AGE extension
- **Why not vector embeddings?** Claude can handle semantic search directly; simpler architecture, one less service
- **Why SQL Graph?** Native to Azure SQL, uses familiar SQL + MATCH syntax, no separate graph database needed
- **Why managed identity?** More secure than connection strings; automatic credential rotation; Azure-native

---

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/project:judge` | Review code for errors and correct folder placement |
| `/project:security` | Security review (secrets, injection, dangerous patterns) |
| `/project:git-state` | Check current git branch and status |
| `/project:phase-status` | Show current phase progress and next steps |
| `/project:systems-check` | Review code against system behavior patterns (retries, idempotency, error handling) |

---

## Commands

```bash
# Test Azure connectivity
python scripts/test_connectivity.py

# Initialize database schema
python scripts/init_db.py

# Run Streamlit app (Phase 5+)
streamlit run app/views/main.py
```

---

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Storage | Azure Blob Storage | Hot tier, ~2GB |
| Database | Azure SQL Database | Basic tier (~$5/month) |
| Graph | SQL Graph (native) | NODE/EDGE tables, MATCH queries |
| Ingestion | Azure Functions | Consumption plan, blob trigger |
| Search & Synthesis | Claude API | Semantic search, concept extraction |
| App | Streamlit | Python-native |
| Hosting | Azure Container Apps | Free tier |

### Estimated Monthly Cost
| Service | Cost |
|---------|------|
| Azure Blob Storage | ~$0.50 |
| Azure SQL Database (Basic) | ~$5.00 |
| Azure Functions (Consumption) | ~$0.00 (free tier) |
| Azure Container Apps | ~$0.00 (free tier) |
| Claude API | Usage-based |
| **Total Azure** | **~$5-6/month** |

---

## Data Model

### Node Tables (Azure SQL Graph)

```sql
-- Sources: PDFs, markdown files, articles
-- Includes status tracking for processing lifecycle
CREATE TABLE sources (
    id INT PRIMARY KEY IDENTITY(1,1),
    title NVARCHAR(500),
    author NVARCHAR(255),
    source_type NVARCHAR(50) NOT NULL,    -- 'pdf', 'markdown', 'article'
    file_path NVARCHAR(500) NOT NULL,     -- Unique key for idempotency
    page_count INT,
    status NVARCHAR(50) NOT NULL,         -- UPLOADED, PARSING, PARSED, EXTRACTING, COMPLETE, *_FAILED
    error_message NVARCHAR(MAX),
    metadata NVARCHAR(MAX),               -- JSON
    created_at DATETIME2, updated_at DATETIME2
) AS NODE;

-- Chunks: text segments from sources
CREATE TABLE chunks (
    id INT PRIMARY KEY IDENTITY(1,1),
    source_id INT NOT NULL,               -- FK to sources
    text NVARCHAR(MAX) NOT NULL,
    position INT NOT NULL,                -- Sequential within source
    page_start INT, page_end INT,
    section NVARCHAR(500),                -- Heading or chapter
    char_count INT NOT NULL,              -- For cost tracking
    metadata NVARCHAR(MAX)
) AS NODE;

-- Concepts: extracted topics and ideas (Phase 3)
CREATE TABLE concepts (
    id INT PRIMARY KEY IDENTITY(1,1),
    name NVARCHAR(255) NOT NULL,          -- Unique, case-insensitive
    description NVARCHAR(MAX),
    category NVARCHAR(100)                -- 'methodology', 'principle', 'tool', etc.
) AS NODE;
```

### Edge Tables

```sql
CREATE TABLE from_source AS EDGE;   -- Chunk → Source (graph traversal)
CREATE TABLE covers (               -- Source → Concept
    weight FLOAT,                   -- Relevance (0-1)
    mention_count INT               -- Frequency
) AS EDGE;
CREATE TABLE mentions (             -- Chunk → Concept
    relevance FLOAT,                -- How central (0-1)
    context NVARCHAR(500)           -- Surrounding text
) AS EDGE;
CREATE TABLE related_to (           -- Concept → Concept
    relationship_type NVARCHAR(100),-- 'similar_to', 'part_of', 'enables'
    strength FLOAT
) AS EDGE;
```

### Example Graph Queries

```sql
-- Find all concepts covered by a source
SELECT s.title, c.name
FROM sources s, covers cov, concepts c
WHERE MATCH(s-(covers)->c)
  AND s.title = 'Data Mesh';

-- Find concepts discussed by multiple authors
SELECT c.name, s1.author, s2.author
FROM sources s1, covers c1, concepts c, covers c2, sources s2
WHERE MATCH(s1-(c1)->c<-(c2)-s2)
  AND s1.author < s2.author;

-- Find related concepts (2 hops from a starting concept)
SELECT c1.name, c2.name, r.strength
FROM concepts c1, related_to r, concepts c2
WHERE MATCH(c1-(related_to)->c2)
  AND c1.name = 'data product';
```

---

## Code Standards

- Python 3.11+
- Type hints on all functions
- Docstrings for public functions
- Keep files under 300 lines
- Environment variables for secrets (never commit .env)
- Run `/project:judge` after writing code
- Run `/project:security` before committing
- **Before committing**: Verify code against System Behavior patterns (failure modes, idempotency, retries, cost controls, observability). Report gaps to user before proceeding.

---

## Log

| Date | Phase | Summary |
|------|-------|---------|
| 2025-12-30 | 1 | Initial architecture, Option A structure, slash commands |
| 2025-12-31 | 1 | Architecture pivot: PostgreSQL → Azure SQL (for SQL Graph), removed pgvector/embeddings in favor of Claude API for search, added Azure Functions for ingestion, generalized schema from books to sources |
| 2025-12-31 | 1→2 | Phase 1 complete. Azure resources created via Portal: Resource Group, Storage Account + container, Function App, SQL Database. Configured managed identity for Function → Storage and Function → SQL. Moved to Phase 2. |
| 2025-12-31 | 2 | Aligned codebase with Azure SQL architecture: rewrote db connection for pyodbc, removed PostgreSQL/pgvector/OpenAI code, restructured pipeline/ → functions/, created function scaffold with blob trigger, updated all scripts and dependencies. Schema deferred until after parsing exploration. |
| 2026-01-01 | 2 | Implemented PDF parsing (PyMuPDF) with metadata and heading extraction. Built chunking system (page-based with size fallback, sentence-aware breaks, overlap). Wired blob trigger to parse and chunk PDFs. Ready to test with sample document. |
| 2026-01-01 | 2 | Added System Behavior section: failure modes, processing states, idempotency, retry patterns, cost controls, observability, invariants, and contracts. Created /project:systems-check command. |
| 2026-01-01 | 2→3 | Phase 2 complete. Implemented SQL Graph schema (3 NODE tables, 4 EDGE tables) with status tracking, idempotency constraints, and cascade deletes. Created init_db.py script and storage.py module. Schema deployed to Azure SQL via Portal. Moving to Phase 3 (concept extraction). |
| 2026-01-01 | 3→4 | Phase 3 complete. Implemented embeddings.py (OpenAI text-embedding-3-small), concepts.py (Claude extraction with retry logic), graph.py (concept storage, mentions/related_to edges). Updated function_app.py with full pipeline (parse → chunk → embed → store → extract). Added background scripts for cross-source and embedding similarity passes. Ready for Phase 4 (Streamlit app). |

---
