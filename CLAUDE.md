# Second Brain: Data Leadership Knowledge System

## Objective

Build a personal knowledge system that ingests PDF books on data team management, enables semantic search across the content, and surfaces relationships between concepts across different authors and books.

**Core question we want to answer**: "What do my books collectively say about topic X, and how do different authors' perspectives relate?"

---

## Architecture Overview

```
Azure Blob Storage (PDFs)
        ↓
   PDF Parser + Chunker
        ↓
   ┌────┴────┐
   ↓         ↓
Embeddings  Concept Extraction
   ↓         ↓
pgvector    Apache AGE (graph)
   └────┬────┘
        ↓
   PostgreSQL (unified store)
        ↓
   Streamlit App (Azure Container Apps)
```

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
├── pipeline/              # BATCH PROCESSING (runs occasionally)
│   ├── ingestion/         # PDF parsing, chunking
│   │   ├── pdf_parser.py
│   │   └── chunker.py
│   ├── embeddings/        # Vector embedding generation
│   │   └── embed.py
│   └── graph/             # Concept extraction, graph building
│       └── concept_extractor.py
│
├── app/                   # INTERACTIVE APP (MVC pattern)
│   ├── models/            # Data classes, view models
│   ├── views/             # Streamlit pages, UI components
│   └── controllers/       # Search logic, orchestration
│
├── shared/                # COMMON CODE (used by both)
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
| `pipeline/` | PDF parsing, embeddings, graph building | Batch ETL scripts |
| `app/` | Streamlit UI, user-facing features | MVC (models/views/controllers) |
| `shared/` | Database, config, utilities | Used by both pipeline and app |
| `scripts/` | One-off tools, setup scripts | CLI utilities |
| `infrastructure/` | Azure IaC, setup guides | DevOps |

---

## Project Phases

### Phase 1: Infrastructure ← CURRENT
- [x] Project structure and CLAUDE.md
- [x] Slash commands for workflow (/judge, /security, /git-state)
- [ ] Azure Blob Storage container for PDFs
- [ ] Azure PostgreSQL Flexible Server (Burstable B1ms)
- [ ] Enable pgvector extension
- [ ] Enable Apache AGE extension
- [ ] Basic connectivity test

### Phase 2: Ingestion Pipeline
- [ ] PDF text extraction (PyMuPDF)
- [ ] Chunking strategy (section/paragraph level)
- [ ] Metadata extraction (title, author, chapter)
- [ ] Store raw chunks in PostgreSQL

### Phase 3: Embeddings & Vector Search
- [ ] OpenAI embedding integration (text-embedding-3-small)
- [ ] Batch embed all chunks
- [ ] pgvector index and similarity search
- [ ] Test semantic queries

### Phase 4: Concept Extraction & Graph
- [ ] LLM-based concept extraction from chunks
- [ ] Define graph schema (Book, Concept, Chunk nodes)
- [ ] Build edges (COVERS, MENTIONS, RELATED_TO)
- [ ] Graph queries (Cypher via AGE)

### Phase 5: Streamlit Application
- [ ] Search interface (semantic + keyword)
- [ ] Concept explorer (graph visualization)
- [ ] Book comparison view
- [ ] Deploy to Azure Container Apps

### Phase 6: Refinement (Future)
- [ ] Highlight extraction if feasible
- [ ] Citation/quote extraction
- [ ] Reading notes integration
- [ ] Chat interface over knowledge base

---

## Current Phase: 1 - Infrastructure

### Detailed Tasks
1. Set up Azure resources via Portal (see infrastructure/AZURE_PORTAL_SETUP.md)
2. Configure environment variables in .env
3. Run connectivity test
4. Initialize database schema

### Decisions Made
- **Option A folder structure**: Separated `pipeline/` (batch) from `app/` (interactive) with `shared/` for common code
- **MVC for app**: The Streamlit app will follow models/views/controllers pattern
- **Slash commands for review**: Using /judge and /security instead of automated hooks

### Open Questions
- Apache AGE availability on Azure PostgreSQL Flexible Server (may need workaround)

---

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/project:judge` | Review code for errors and correct folder placement |
| `/project:security` | Security review (secrets, injection, dangerous patterns) |
| `/project:git-state` | Check current git branch and status |
| `/project:phase-status` | Show current phase progress and next steps |

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
| Database | Azure PostgreSQL Flexible | B1ms burstable |
| Vector | pgvector extension | Cosine similarity |
| Graph | Apache AGE extension | Cypher queries |
| Embeddings | OpenAI text-embedding-3-small | ~$0.02/1M tokens |
| Concept Extraction | Claude API or GPT-4o-mini | One-time batch |
| App | Streamlit | Python-native |
| Hosting | Azure Container Apps | Free tier |

---

## Data Model

### PostgreSQL Tables

```sql
books (id, title, author, file_path, uploaded_at)
chunks (id, book_id, chapter, section, text, page_start, page_end, embedding vector(1536))
concepts (id, name, description, category)
chunk_concepts (chunk_id, concept_id, relevance_score)
```

### Graph Schema (Apache AGE)

```
(:Book {id, title, author})
(:Concept {id, name, description})
(:Chunk {id, text_preview})

(:Book)-[:COVERS {weight}]->(:Concept)
(:Chunk)-[:MENTIONS]->(:Concept)
(:Concept)-[:RELATED_TO {weight}]->(:Concept)
(:Chunk)-[:FROM]->(:Book)
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

---

## Log

| Date | Phase | Summary |
|------|-------|---------|
| 2024-12-31 | 1 | Initial architecture, Option A structure, slash commands |

---
