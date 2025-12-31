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

## Project Phases

### Phase 1: Infrastructure
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
_To be filled in as we begin this phase_

### Decisions Made
_Document key choices here as we go_

### Open Questions
_Parking lot for things to resolve_

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
-- Core content
books (id, title, author, file_path, uploaded_at)
chunks (id, book_id, chapter, section, text, page_start, page_end, embedding vector(1536))

-- Graph handled via AGE, but conceptually:
-- Nodes: Book, Concept, Chunk
-- Edges: COVERS, MENTIONS, RELATED_TO (with weight)
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

## Commands

```bash
# TBD - will add as we build
```

---

## Code Standards

- Python 3.11+
- Use `uv` or `pip` for dependencies
- Type hints on all functions
- Docstrings for public functions
- Keep files under 300 lines
- Environment variables for secrets (never commit)

---

## File Structure

```
second-brain/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .env.example
├── infrastructure/
│   └── (Bicep/Terraform for Azure resources)
├── src/
│   ├── ingestion/
│   │   ├── pdf_parser.py
│   │   └── chunker.py
│   ├── embeddings/
│   │   └── embed.py
│   ├── graph/
│   │   └── concept_extractor.py
│   ├── db/
│   │   └── models.py
│   └── app/
│       └── streamlit_app.py
├── scripts/
│   └── (one-off utilities)
└── tests/
```

---

## Log

| Date | Phase | Summary |
|------|-------|---------|
| _today_ | Planning | Initial architecture and CLAUDE.md created |

---
