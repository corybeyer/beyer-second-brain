# Second Brain

A personal knowledge management system for surfacing insights and relationships across a library of data leadership documents (PDFs, markdown).

## Quick Start

_Phase 2 in progress - ingestion pipeline development_

## Project Status

See [CLAUDE.md](./CLAUDE.md) for detailed project plan and current phase.

**Current Phase**: 2 - Ingestion Pipeline

## Overview

This system:
1. Ingests documents (PDFs, markdown) into Azure Blob Storage
2. Triggers Azure Function to parse and chunk content
3. Stores chunks in Azure SQL Database
4. Extracts concepts and builds a knowledge graph (SQL Graph)
5. Uses Claude API for semantic search and synthesis
6. Provides a Streamlit interface for exploration

## Architecture

```
Documents → Blob Storage → Azure Function → Azure SQL (+ SQL Graph) → Claude API → Streamlit
```

## Azure Resources

| Resource | Name | Purpose |
|----------|------|---------|
| Resource Group | `rg-second-brain` | Container for project resources |
| Storage Account | `stsecondbrain` | Document storage |
| Function App | `func-secondbrain` | Blob-triggered ingestion |
| SQL Database | `secondbrain` | Chunks + SQL Graph |

## License

Private project - not for distribution.
