# Second Brain: Data Leadership Knowledge System

A personal knowledge management system for surfacing insights and relationships across a library of data team management books.

## Quick Start

_Coming soon - infrastructure setup in progress_

## Project Status

See [CLAUDE.md](./CLAUDE.md) for detailed project plan and current phase.

## Overview

This system:
1. Ingests PDF books into Azure Blob Storage
2. Parses and chunks content for processing
3. Creates embeddings for semantic search (pgvector)
4. Extracts concepts and builds a knowledge graph (Apache AGE)
5. Provides a Streamlit interface for exploration

## Architecture

```
PDFs → Blob Storage → Parser → Embeddings + Graph → PostgreSQL → Streamlit
```

## License

Private project - not for distribution.
