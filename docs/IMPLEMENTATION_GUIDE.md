# Second Brain Implementation Guide

Complete technical guide for the document ingestion, embedding, concept extraction, and knowledge graph pipeline.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Pipeline Architecture](#pipeline-architecture)
3. [Schema Reference](#schema-reference)
4. [Step 1: Parse & Chunk](#step-1-parse--chunk)
5. [Step 2: Generate Embeddings](#step-2-generate-embeddings)
6. [Step 3: Store Documents](#step-3-store-documents)
7. [Step 4: Extract Concepts (Per-Chunk)](#step-4-extract-concepts-per-chunk)
8. [Step 5: Source-Level Relationship Pass](#step-5-source-level-relationship-pass)
9. [Step 6: Cross-Source Relationship Pass](#step-6-cross-source-relationship-pass)
10. [Step 7: Embedding Similarity Pass](#step-7-embedding-similarity-pass)
11. [Query Patterns](#query-patterns)
12. [Cost Estimates](#cost-estimates)
13. [Error Handling & Retries](#error-handling--retries)

---

## System Overview

### What This System Does

1. **Ingests** PDFs and markdown files about data leadership/management
2. **Chunks** documents into searchable segments
3. **Embeds** chunks for semantic similarity search
4. **Extracts** concepts and relationships using Claude
5. **Builds** a knowledge graph connecting concepts across sources
6. **Enables** semantic search and cross-source synthesis

### Core Question We Answer

> "What do my sources collectively say about topic X, and how do different authors' perspectives relate?"

### Technologies

| Component | Technology | Purpose |
|-----------|------------|---------|
| Storage | Azure Blob Storage | Document storage |
| Trigger | Azure Functions | Blob-triggered processing |
| Database | Azure SQL Database | Chunks, concepts, graph |
| Graph | SQL Graph (NODE/EDGE) | Relationship traversal |
| Embeddings | OpenAI text-embedding-3-small | Semantic similarity |
| Extraction | Claude API | Concept & relationship extraction |
| Search | VECTOR_DISTANCE + Graph queries | Hybrid retrieval |

---

## Pipeline Architecture

### Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DOCUMENT UPLOAD                                     │
│                    PDF uploaded to Azure Blob Storage                            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: PARSE & CHUNK                                                            │
│                                                                                  │
│   PDF bytes ──► PyMuPDF ──► ParsedDocument ──► Chunker ──► List[Chunk]          │
│                                                                                  │
│   Output: 50-200 chunks per document, ~2000 chars each                          │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: GENERATE EMBEDDINGS (OpenAI API)                                         │
│                                                                                  │
│   For each chunk.text ──► OpenAI text-embedding-3-small ──► Vector[1536]        │
│                                                                                  │
│   Output: Each chunk now has .embedding = [0.12, -0.45, 0.89, ...]              │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: STORE IN DATABASE (Azure SQL)                                            │
│                                                                                  │
│   Transaction:                                                                   │
│   ├── DELETE existing source (idempotency)                                      │
│   ├── INSERT INTO sources (...) → source_id                                     │
│   ├── INSERT INTO chunks (text, embedding, position, ...) for each chunk        │
│   ├── INSERT INTO from_source edges (chunk → source)                            │
│   └── UPDATE sources SET status = 'PARSED'                                      │
│                                                                                  │
│   Output: source_id, chunk IDs stored                                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: EXTRACT CONCEPTS - PER CHUNK (Claude API)                                │
│                                                                                  │
│   For each chunk:                                                                │
│   ├── Send chunk.text to Claude with extraction prompt                          │
│   ├── Claude returns: {concepts: [...], relationships: [...]}                   │
│   ├── MERGE concepts into concepts table (upsert by name)                       │
│   ├── INSERT mentions edges (chunk → concept)                                   │
│   └── INSERT related_to edges (concept → concept) from same chunk               │
│                                                                                  │
│   Output: Concepts and within-chunk relationships stored                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: SOURCE-LEVEL RELATIONSHIP PASS (Claude API)                              │
│                                                                                  │
│   After all chunks processed:                                                    │
│   ├── Query all concepts mentioned in this source                               │
│   ├── Send concept list to Claude: "Find relationships between these"          │
│   ├── INSERT related_to edges for concepts in same source                       │
│   └── INSERT covers edges (source → concept) with weights                       │
│                                                                                  │
│   Output: Source-level concept relationships                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: MARK COMPLETE                                                            │
│                                                                                  │
│   UPDATE sources SET status = 'COMPLETE' WHERE id = @source_id                  │
│                                                                                  │
│   Output: Document fully processed and queryable                                 │
└─────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────┐
│ PERIODIC: CROSS-SOURCE RELATIONSHIP PASS (Background Job)                        │
│                                                                                  │
│   Run after N new sources or on schedule:                                        │
│   ├── Find concepts appearing in multiple sources                               │
│   ├── Ask Claude to identify cross-source relationships                         │
│   └── INSERT related_to edges spanning sources                                  │
└─────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────┐
│ PERIODIC: EMBEDDING SIMILARITY PASS (Background Job)                             │
│                                                                                  │
│   Run periodically:                                                              │
│   ├── Generate embeddings for concept descriptions                              │
│   ├── Compare all concept pairs via cosine similarity                           │
│   └── INSERT similar_to edges where similarity > 0.85                           │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Schema Reference

### NODE Tables

```sql
-- Sources: Documents (PDFs, markdown, articles)
CREATE TABLE sources (
    id INT PRIMARY KEY IDENTITY(1,1),
    title NVARCHAR(500),
    author NVARCHAR(255),
    source_type NVARCHAR(50) NOT NULL,      -- 'pdf', 'markdown', 'article'
    file_path NVARCHAR(500) NOT NULL,       -- Unique key for idempotency
    page_count INT,
    status NVARCHAR(50) NOT NULL,           -- Processing state
    error_message NVARCHAR(MAX),
    metadata NVARCHAR(MAX),                 -- JSON
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE(),
    CONSTRAINT UQ_sources_file_path UNIQUE (file_path),
    CONSTRAINT CK_sources_status CHECK (status IN (
        'UPLOADED', 'PARSING', 'PARSED', 'EXTRACTING', 'COMPLETE',
        'PARSE_FAILED', 'EXTRACT_FAILED'
    ))
) AS NODE;

-- Chunks: Text segments with embeddings
CREATE TABLE chunks (
    id INT PRIMARY KEY IDENTITY(1,1),
    source_id INT NOT NULL,
    text NVARCHAR(MAX) NOT NULL,
    position INT NOT NULL,                  -- Sequential within source
    page_start INT,
    page_end INT,
    section NVARCHAR(500),                  -- Heading or chapter
    char_count INT NOT NULL,
    embedding VECTOR(1536),                 -- OpenAI embedding
    metadata NVARCHAR(MAX),
    created_at DATETIME2 DEFAULT GETDATE(),
    CONSTRAINT FK_chunks_source FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    CONSTRAINT UQ_chunks_position UNIQUE (source_id, position)
) AS NODE;

-- Concepts: Extracted topics and ideas
CREATE TABLE concepts (
    id INT PRIMARY KEY IDENTITY(1,1),
    name NVARCHAR(255) NOT NULL,            -- Unique, case-insensitive
    description NVARCHAR(MAX),
    category NVARCHAR(100),                 -- 'methodology', 'principle', etc.
    embedding VECTOR(1536),                 -- For similarity search
    created_at DATETIME2 DEFAULT GETDATE(),
    updated_at DATETIME2 DEFAULT GETDATE()
) AS NODE;

CREATE UNIQUE INDEX UQ_concepts_name ON concepts(name);
```

### EDGE Tables

```sql
-- from_source: Chunk belongs to Source
CREATE TABLE from_source AS EDGE;

-- covers: Source covers Concept (aggregated after processing)
CREATE TABLE covers (
    weight FLOAT,                           -- Relevance (0-1)
    mention_count INT                       -- How many chunks mention it
) AS EDGE;

-- mentions: Chunk mentions Concept
CREATE TABLE mentions (
    relevance FLOAT,                        -- How central (0-1)
    context NVARCHAR(500)                   -- Surrounding text snippet
) AS EDGE;

-- related_to: Concept relates to Concept
CREATE TABLE related_to (
    relationship_type NVARCHAR(100),        -- 'enables', 'requires', 'part_of', etc.
    strength FLOAT,                         -- Confidence (0-1)
    source_id INT                           -- Which source established this
) AS EDGE;
```

### Processing States

```
UPLOADED → PARSING → PARSED → EXTRACTING → COMPLETE
              ↓                    ↓
         PARSE_FAILED       EXTRACT_FAILED
```

---

## Step 1: Parse & Chunk

### Code Location
- `functions/shared/parser.py` - PDF parsing
- `functions/shared/chunker.py` - Text chunking

### Parser Output

```python
@dataclass
class ParsedDocument:
    filename: str
    title: str | None          # From PDF metadata
    author: str | None         # From PDF metadata
    page_count: int
    pages: list[PageContent]   # Text + headings per page
    metadata: dict             # Raw PDF metadata
```

### Chunker Output

```python
@dataclass
class Chunk:
    text: str                  # Chunk content
    position: int              # 0, 1, 2, ... within document
    page_start: int | None     # Starting page number
    page_end: int | None       # Ending page number
    section: str | None        # Heading if detected
```

### Chunking Strategy

1. **Page-based** (preferred): If a page fits in max_chunk_size (2000 chars), use whole page
2. **Size-based fallback**: Large pages split with:
   - Sentence-aware breaks (prefer `. `, `! `, `? `)
   - Paragraph breaks (`\n\n`)
   - Word boundaries
   - Overlap between chunks (200 chars default)

### Usage

```python
from shared.parser import parse_pdf
from shared.chunker import chunk_document

# Parse PDF
doc = parse_pdf(pdf_bytes, filename="data-mesh.pdf")

# Chunk document
chunks = chunk_document(doc, max_chunk_size=2000, overlap=200)
# Returns: List[Chunk] with 50-200 chunks typically
```

---

## Step 2: Generate Embeddings

### Provider
OpenAI `text-embedding-3-small` (1536 dimensions)

### Code

```python
# functions/shared/embeddings.py

from openai import OpenAI
import os

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def get_embedding(text: str) -> list[float]:
    """Generate embedding for a single text."""
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding


def get_embeddings_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Generate embeddings for multiple texts efficiently.

    OpenAI supports up to 2048 inputs per request.
    We batch to control memory and handle rate limits.
    """
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            input=batch,
            model="text-embedding-3-small"
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
```

### Integration with Chunks

```python
def embed_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Add embeddings to all chunks."""
    texts = [chunk.text for chunk in chunks]
    embeddings = get_embeddings_batch(texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding

    return chunks
```

### Cost

| Model | Dimensions | Cost per 1M tokens |
|-------|------------|-------------------|
| text-embedding-3-small | 1536 | $0.02 |
| text-embedding-3-large | 3072 | $0.13 |

Typical document (~100 chunks × 500 tokens): ~$0.001

---

## Step 3: Store Documents

### Code Location
- `functions/shared/storage.py`

### Implementation

```python
# functions/shared/storage.py

import json
from shared.db.connection import get_db_cursor


def store_document(
    doc: ParsedDocument,
    chunks: list[Chunk],
    file_path: str
) -> int:
    """Store source and chunks with embeddings. Idempotent via delete-and-replace."""

    with get_db_cursor(commit=True) as cursor:
        # === IDEMPOTENCY: Delete existing if present ===
        cursor.execute("DELETE FROM sources WHERE file_path = ?", (file_path,))

        # === INSERT SOURCE ===
        source_type = "pdf" if file_path.lower().endswith(".pdf") else "markdown"
        metadata_json = json.dumps(doc.metadata) if doc.metadata else None

        cursor.execute("""
            INSERT INTO sources (
                title, author, source_type, file_path, page_count, status, metadata
            )
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, 'PARSED', ?)
        """, (doc.title, doc.author, source_type, file_path, doc.page_count, metadata_json))

        source_id = cursor.fetchone()[0]

        # === INSERT CHUNKS WITH EMBEDDINGS ===
        for chunk in chunks:
            embedding_json = json.dumps(chunk.embedding) if chunk.embedding else None

            cursor.execute("""
                INSERT INTO chunks (
                    source_id, text, position, page_start, page_end,
                    section, char_count, embedding
                )
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS VECTOR(1536)))
            """, (
                source_id,
                chunk.text,
                chunk.position,
                chunk.page_start,
                chunk.page_end,
                chunk.section,
                len(chunk.text),
                embedding_json
            ))

            chunk.id = cursor.fetchone()[0]

        # === CREATE from_source EDGES ===
        cursor.execute("""
            INSERT INTO from_source ($from_id, $to_id)
            SELECT c.$node_id, s.$node_id
            FROM chunks c, sources s
            WHERE c.source_id = ? AND s.id = ?
        """, (source_id, source_id))

        return source_id
```

---

## Step 4: Extract Concepts (Per-Chunk)

### Purpose
Extract concepts and relationships from each chunk of text.

### Extraction Prompt

```python
# functions/shared/concepts.py

EXTRACTION_PROMPT = """You are extracting concepts from text about data management and leadership.

## CONCEPT CATEGORIES (only use these)
- methodology: frameworks, approaches (e.g., "data mesh", "agile", "scrum")
- principle: core beliefs, guiding rules (e.g., "domain ownership", "single responsibility")
- pattern: recurring solutions (e.g., "event sourcing", "CQRS", "data product")
- role: people, teams, responsibilities (e.g., "data product owner", "platform team")
- tool: technologies, products (e.g., "dbt", "Kafka", "Snowflake")
- metric: measurements, KPIs (e.g., "data quality score", "lead time")

## RELATIONSHIP TYPES (only use these)
- enables: A makes B possible (e.g., "domain ownership enables data product")
- requires: A depends on B (e.g., "data product requires clear ownership")
- part_of: A is a component of B (e.g., "schema is part_of data product")
- similar_to: A is conceptually like B (e.g., "data mesh similar_to microservices")
- contrasts: A is the opposite of B (e.g., "centralized contrasts federated")

## RULES
1. Only extract SPECIFIC concepts that are REUSABLE across documents
2. Do NOT extract generic terms: "data", "team", "process", "system", "organization"
3. Normalize names: lowercase, singular form (e.g., "data product" not "Data Products")
4. Only create relationships explicitly stated or strongly implied in the text
5. Include a brief description for each concept

## TEXT TO ANALYZE
\"\"\"
{text}
\"\"\"

## RESPONSE FORMAT
Return valid JSON only, no other text:
{{
  "concepts": [
    {{"name": "concept name", "category": "category", "description": "brief description"}}
  ],
  "relationships": [
    {{"from": "concept1", "to": "concept2", "type": "relationship_type"}}
  ]
}}
"""
```

### Extraction Code

```python
# functions/shared/concepts.py

import anthropic
import json
from typing import TypedDict

client = anthropic.Anthropic()


class Concept(TypedDict):
    name: str
    category: str
    description: str


class Relationship(TypedDict):
    from_concept: str  # 'from' is reserved in Python
    to_concept: str
    type: str


class ExtractionResult(TypedDict):
    concepts: list[Concept]
    relationships: list[Relationship]


def extract_concepts_from_chunk(text: str) -> ExtractionResult:
    """Extract concepts and relationships from a chunk of text.

    Args:
        text: Chunk text to analyze

    Returns:
        ExtractionResult with concepts and relationships
    """
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": EXTRACTION_PROMPT.format(text=text)
        }]
    )

    # Parse JSON response
    content = response.content[0].text
    result = json.loads(content)

    # Normalize the relationships key
    relationships = []
    for rel in result.get("relationships", []):
        relationships.append({
            "from_concept": rel["from"],
            "to_concept": rel["to"],
            "type": rel["type"]
        })

    return {
        "concepts": result.get("concepts", []),
        "relationships": relationships
    }
```

### Store Extraction Results

```python
# functions/shared/graph.py

def store_chunk_extraction(
    cursor,
    chunk_id: int,
    source_id: int,
    extraction: ExtractionResult
) -> None:
    """Store extracted concepts and create graph edges.

    Args:
        cursor: Database cursor
        chunk_id: ID of the chunk
        source_id: ID of the source document
        extraction: Concepts and relationships from Claude
    """

    # === UPSERT CONCEPTS ===
    for concept in extraction["concepts"]:
        cursor.execute("""
            MERGE INTO concepts AS target
            USING (SELECT ? AS name, ? AS category, ? AS description) AS source
            ON LOWER(target.name) = LOWER(source.name)
            WHEN MATCHED THEN
                UPDATE SET
                    description = COALESCE(source.description, target.description),
                    updated_at = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (name, category, description, created_at, updated_at)
                VALUES (source.name, source.category, source.description, GETDATE(), GETDATE());
        """, (concept["name"], concept["category"], concept["description"]))

    # === CREATE mentions EDGES (chunk → concept) ===
    for concept in extraction["concepts"]:
        # Get first 200 chars of chunk as context
        cursor.execute("SELECT LEFT(text, 200) FROM chunks WHERE id = ?", (chunk_id,))
        context = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO mentions ($from_id, $to_id, relevance, context)
            SELECT c.$node_id, con.$node_id, 0.8, ?
            FROM chunks c, concepts con
            WHERE c.id = ? AND LOWER(con.name) = LOWER(?)
        """, (context, chunk_id, concept["name"]))

    # === CREATE related_to EDGES (concept → concept) ===
    for rel in extraction["relationships"]:
        cursor.execute("""
            -- Only insert if both concepts exist and edge doesn't exist
            INSERT INTO related_to ($from_id, $to_id, relationship_type, strength, source_id)
            SELECT c1.$node_id, c2.$node_id, ?, 0.8, ?
            FROM concepts c1, concepts c2
            WHERE LOWER(c1.name) = LOWER(?)
              AND LOWER(c2.name) = LOWER(?)
              AND NOT EXISTS (
                  SELECT 1 FROM related_to r
                  WHERE r.$from_id = c1.$node_id
                    AND r.$to_id = c2.$node_id
                    AND r.relationship_type = ?
              )
        """, (rel["type"], source_id, rel["from_concept"], rel["to_concept"], rel["type"]))
```

### Process All Chunks

```python
def process_chunks_for_concepts(cursor, source_id: int, chunks: list[Chunk]) -> None:
    """Extract concepts from all chunks of a source."""

    # Update status
    cursor.execute(
        "UPDATE sources SET status = 'EXTRACTING' WHERE id = ?",
        (source_id,)
    )

    for chunk in chunks:
        try:
            extraction = extract_concepts_from_chunk(chunk.text)
            store_chunk_extraction(cursor, chunk.id, source_id, extraction)
        except Exception as e:
            # Log but continue with other chunks
            logger.warning(f"Concept extraction failed for chunk {chunk.id}: {e}")
            continue
```

---

## Step 5: Source-Level Relationship Pass

### Purpose
After all chunks are processed, find relationships between concepts that appear in the same source but weren't in the same chunk.

### When It Runs
Immediately after all chunks from a source have been processed.

### Implementation

```python
# functions/shared/graph.py

SOURCE_RELATIONSHIP_PROMPT = """These concepts all appear in the same book/document about data management.
Identify meaningful relationships between them.

## RELATIONSHIP TYPES
- enables: A makes B possible
- requires: A depends on B
- part_of: A is a component of B
- similar_to: A is conceptually similar to B
- contrasts: A is the opposite of B

## CONCEPTS FROM THIS SOURCE
{concepts_list}

## RULES
1. Only identify relationships that are meaningful and likely true
2. Don't force relationships - it's okay to return few or none
3. Focus on the most important/obvious relationships
4. Consider how these concepts would relate in data management context

## RESPONSE FORMAT
Return valid JSON array only:
[
  {{"from": "concept1", "to": "concept2", "type": "relationship_type"}}
]

If no clear relationships, return: []
"""


def source_level_relationship_pass(cursor, source_id: int) -> int:
    """Find relationships between all concepts in a source.

    Args:
        cursor: Database cursor
        source_id: ID of the source to process

    Returns:
        Number of relationships created
    """

    # Get all concepts mentioned in this source
    cursor.execute("""
        SELECT DISTINCT con.name, con.category, con.description
        FROM chunks c
        JOIN mentions m ON m.$from_id = c.$node_id
        JOIN concepts con ON m.$to_id = con.$node_id
        WHERE c.source_id = ?
        ORDER BY con.name
    """, (source_id,))

    concepts = cursor.fetchall()

    if len(concepts) < 2:
        return 0  # Need at least 2 concepts for relationships

    # Format concepts for prompt
    concepts_list = "\n".join([
        f"- {row[0]} ({row[1]}): {row[2] or 'No description'}"
        for row in concepts
    ])

    # Ask Claude to identify relationships
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": SOURCE_RELATIONSHIP_PROMPT.format(concepts_list=concepts_list)
        }]
    )

    relationships = json.loads(response.content[0].text)

    # Store new relationships
    created = 0
    for rel in relationships:
        cursor.execute("""
            -- Insert if edge doesn't already exist
            INSERT INTO related_to ($from_id, $to_id, relationship_type, strength, source_id)
            SELECT c1.$node_id, c2.$node_id, ?, 0.7, ?
            FROM concepts c1, concepts c2
            WHERE LOWER(c1.name) = LOWER(?)
              AND LOWER(c2.name) = LOWER(?)
              AND NOT EXISTS (
                  SELECT 1 FROM related_to r
                  WHERE r.$from_id = c1.$node_id
                    AND r.$to_id = c2.$node_id
              )
        """, (rel["type"], source_id, rel["from"], rel["to"]))

        if cursor.rowcount > 0:
            created += 1

    return created
```

### Create Covers Edges

After all concept extraction is done, aggregate which concepts a source covers:

```python
def create_covers_edges(cursor, source_id: int) -> int:
    """Create covers edges showing which concepts a source discusses.

    Args:
        cursor: Database cursor
        source_id: ID of the source

    Returns:
        Number of covers edges created
    """

    # Get total chunk count for weight calculation
    cursor.execute(
        "SELECT COUNT(*) FROM chunks WHERE source_id = ?",
        (source_id,)
    )
    total_chunks = cursor.fetchone()[0]

    if total_chunks == 0:
        return 0

    # Create covers edges with weight based on mention frequency
    cursor.execute("""
        INSERT INTO covers ($from_id, $to_id, weight, mention_count)
        SELECT
            s.$node_id,
            con.$node_id,
            CAST(COUNT(DISTINCT c.id) AS FLOAT) / ?,  -- weight = frequency
            COUNT(DISTINCT c.id)                       -- mention_count
        FROM sources s
        JOIN chunks c ON c.source_id = s.id
        JOIN mentions m ON m.$from_id = c.$node_id
        JOIN concepts con ON m.$to_id = con.$node_id
        WHERE s.id = ?
        GROUP BY s.$node_id, con.$node_id
    """, (total_chunks, source_id))

    return cursor.rowcount
```

---

## Step 6: Cross-Source Relationship Pass

### Purpose
Find relationships between concepts that span multiple sources. Run periodically, not during ingestion.

### When It Runs
- After N new sources (e.g., every 5 sources)
- On a schedule (e.g., weekly)
- On-demand via script

### Implementation

```python
# scripts/cross_source_pass.py

CROSS_SOURCE_PROMPT = """These concepts appear across multiple books/sources about data management.
The sources they appear in are listed. Identify relationships between concepts from DIFFERENT sources.

## RELATIONSHIP TYPES
- enables: A makes B possible
- requires: A depends on B
- part_of: A is a component of B
- similar_to: A is conceptually similar to B
- contrasts: A is the opposite of B

## CONCEPTS AND THEIR SOURCES
{concepts_with_sources}

## RULES
1. Focus on relationships between concepts from DIFFERENT sources
2. These relationships show how ideas from different authors connect
3. Be conservative - only identify clear relationships
4. Consider how concepts from different books might complement or contrast

## RESPONSE FORMAT
Return valid JSON array:
[
  {{"from": "concept1", "to": "concept2", "type": "relationship_type", "reason": "brief explanation"}}
]
"""


def cross_source_relationship_pass(cursor) -> int:
    """Find relationships between concepts spanning multiple sources.

    Returns:
        Number of new relationships created
    """

    # Find concepts that appear in 2+ sources
    cursor.execute("""
        SELECT
            con.name,
            con.category,
            con.description,
            STRING_AGG(s.title, ' | ') as sources
        FROM concepts con
        JOIN covers cov ON cov.$to_id = con.$node_id
        JOIN sources s ON cov.$from_id = s.$node_id
        GROUP BY con.id, con.name, con.category, con.description
        HAVING COUNT(DISTINCT s.id) >= 2
        ORDER BY COUNT(DISTINCT s.id) DESC
    """)

    shared_concepts = cursor.fetchall()

    if len(shared_concepts) < 2:
        return 0

    # Format for prompt
    concepts_with_sources = "\n".join([
        f"- {row[0]} ({row[1]}): appears in [{row[3]}]"
        for row in shared_concepts
    ])

    # Ask Claude
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": CROSS_SOURCE_PROMPT.format(concepts_with_sources=concepts_with_sources)
        }]
    )

    relationships = json.loads(response.content[0].text)

    # Store relationships
    created = 0
    for rel in relationships:
        cursor.execute("""
            INSERT INTO related_to ($from_id, $to_id, relationship_type, strength, source_id)
            SELECT c1.$node_id, c2.$node_id, ?, 0.6, NULL  -- NULL source_id = cross-source
            FROM concepts c1, concepts c2
            WHERE LOWER(c1.name) = LOWER(?)
              AND LOWER(c2.name) = LOWER(?)
              AND NOT EXISTS (
                  SELECT 1 FROM related_to r
                  WHERE r.$from_id = c1.$node_id AND r.$to_id = c2.$node_id
              )
        """, (rel["type"], rel["from"], rel["to"]))

        if cursor.rowcount > 0:
            created += 1

    return created
```

---

## Step 7: Embedding Similarity Pass

### Purpose
Find semantically similar concepts using embedding similarity, even if they use different terminology.

### When It Runs
Background job, after concepts have descriptions.

### Implementation

```python
# scripts/embedding_similarity_pass.py

import numpy as np
from shared.embeddings import get_embeddings_batch


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def embedding_similarity_pass(cursor, similarity_threshold: float = 0.85) -> int:
    """Create similar_to edges based on concept embedding similarity.

    Args:
        cursor: Database cursor
        similarity_threshold: Minimum similarity to create edge (0-1)

    Returns:
        Number of new relationships created
    """

    # Get concepts without embeddings and generate them
    cursor.execute("""
        SELECT id, name, description
        FROM concepts
        WHERE description IS NOT NULL AND embedding IS NULL
    """)
    concepts_to_embed = cursor.fetchall()

    if concepts_to_embed:
        texts = [f"{row[1]}: {row[2]}" for row in concepts_to_embed]
        embeddings = get_embeddings_batch(texts)

        for (concept_id, _, _), embedding in zip(concepts_to_embed, embeddings):
            embedding_json = json.dumps(embedding)
            cursor.execute("""
                UPDATE concepts
                SET embedding = CAST(? AS VECTOR(1536))
                WHERE id = ?
            """, (embedding_json, concept_id))

    # Get all concepts with embeddings
    cursor.execute("""
        SELECT id, name, embedding
        FROM concepts
        WHERE embedding IS NOT NULL
    """)
    concepts = cursor.fetchall()

    # Parse embeddings
    concept_data = []
    for row in concepts:
        concept_data.append({
            "id": row[0],
            "name": row[1],
            "embedding": json.loads(row[2]) if isinstance(row[2], str) else list(row[2])
        })

    # Compare all pairs
    created = 0
    for i, c1 in enumerate(concept_data):
        for c2 in concept_data[i+1:]:
            similarity = cosine_similarity(c1["embedding"], c2["embedding"])

            if similarity >= similarity_threshold:
                # Check if relationship already exists
                cursor.execute("""
                    SELECT 1 FROM related_to r, concepts a, concepts b
                    WHERE r.$from_id = a.$node_id AND r.$to_id = b.$node_id
                      AND a.id = ? AND b.id = ?
                """, (c1["id"], c2["id"]))

                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO related_to ($from_id, $to_id, relationship_type, strength)
                        SELECT a.$node_id, b.$node_id, 'similar_to', ?
                        FROM concepts a, concepts b
                        WHERE a.id = ? AND b.id = ?
                    """, (similarity, c1["id"], c2["id"]))
                    created += 1

    return created
```

---

## Query Patterns

### Semantic Search (Find Similar Chunks)

```sql
-- Find chunks similar to a query
DECLARE @query_embedding VECTOR(1536) = CAST(@query_json AS VECTOR(1536));

SELECT TOP 10
    c.id,
    c.text,
    c.section,
    c.page_start,
    s.title,
    s.author,
    VECTOR_DISTANCE('cosine', c.embedding, @query_embedding) as distance
FROM chunks c
JOIN sources s ON c.source_id = s.id
WHERE c.embedding IS NOT NULL
ORDER BY VECTOR_DISTANCE('cosine', c.embedding, @query_embedding);
```

### Graph: Concepts from Same Source

```sql
-- Find all concepts covered by a source
SELECT c.name, c.category, cov.weight, cov.mention_count
FROM sources s, covers cov, concepts c
WHERE MATCH(s-(cov)->c)
  AND s.title = 'Data Mesh'
ORDER BY cov.weight DESC;
```

### Graph: Related Concepts

```sql
-- Find concepts related to a given concept
SELECT c2.name, r.relationship_type, r.strength
FROM concepts c1, related_to r, concepts c2
WHERE MATCH(c1-(r)->c2)
  AND c1.name = 'domain ownership';
```

### Graph: Concepts Shared Across Sources

```sql
-- Find concepts that appear in multiple sources
SELECT c.name, COUNT(DISTINCT s.id) as source_count, STRING_AGG(s.title, ', ') as sources
FROM concepts c, covers cov, sources s
WHERE MATCH(s-(cov)->c)
GROUP BY c.id, c.name
HAVING COUNT(DISTINCT s.id) > 1
ORDER BY source_count DESC;
```

### Graph: Path Between Concepts

```sql
-- Find how two concepts connect (2 hops)
SELECT c1.name, r1.relationship_type, c2.name, r2.relationship_type, c3.name
FROM concepts c1, related_to r1, concepts c2, related_to r2, concepts c3
WHERE MATCH(c1-(r1)->c2-(r2)->c3)
  AND c1.name = 'data mesh'
  AND c3.name = 'platform team';
```

### Hybrid: Semantic + Graph

```python
def hybrid_search(query: str, cursor) -> dict:
    """Combine semantic search with graph traversal."""

    # 1. Embed query
    query_embedding = get_embedding(query)
    query_json = json.dumps(query_embedding)

    # 2. Find similar chunks
    cursor.execute("""
        SELECT TOP 10 c.id, c.text, c.section, s.title, s.author
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        ORDER BY VECTOR_DISTANCE('cosine', c.embedding, CAST(? AS VECTOR(1536)))
    """, (query_json,))
    chunks = cursor.fetchall()

    # 3. Get concepts mentioned in these chunks
    chunk_ids = [c[0] for c in chunks]
    cursor.execute("""
        SELECT DISTINCT con.name, con.category
        FROM chunks c, mentions m, concepts con
        WHERE MATCH(c-(m)->con)
          AND c.id IN ({})
    """.format(','.join('?' * len(chunk_ids))), chunk_ids)
    concepts = cursor.fetchall()

    # 4. Get related concepts (1 hop)
    concept_names = [c[0] for c in concepts]
    cursor.execute("""
        SELECT DISTINCT c2.name, r.relationship_type
        FROM concepts c1, related_to r, concepts c2
        WHERE MATCH(c1-(r)->c2)
          AND c1.name IN ({})
    """.format(','.join('?' * len(concept_names))), concept_names)
    related = cursor.fetchall()

    return {
        "chunks": chunks,
        "concepts": concepts,
        "related_concepts": related
    }
```

---

## Cost Estimates

### Per Document (100 chunks)

| Step | API | Calls | Cost |
|------|-----|-------|------|
| Embeddings | OpenAI | 1 batch | ~$0.001 |
| Per-chunk extraction | Claude | 100 | ~$0.50 |
| Source-level pass | Claude | 1 | ~$0.01 |
| **Total per document** | | | **~$0.51** |

### Periodic Jobs

| Job | Frequency | Cost |
|-----|-----------|------|
| Cross-source pass | Weekly | ~$0.05 |
| Embedding similarity | Weekly | ~$0.01 |

### Monthly Estimate (10 documents/month)

| Item | Cost |
|------|------|
| Document processing | ~$5.10 |
| Periodic jobs | ~$0.24 |
| Azure SQL | ~$5.00 |
| Azure Functions | ~$0.00 |
| Azure Blob | ~$0.50 |
| **Total** | **~$11/month** |

---

## Error Handling & Retries

### Claude API Retries

```python
import time
from anthropic import RateLimitError, APIError


def call_claude_with_retry(prompt: str, max_retries: int = 3) -> str:
    """Call Claude API with exponential backoff retry."""

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text

        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) * 2  # 2s, 4s, 8s
                time.sleep(wait)
            else:
                raise

        except APIError as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise
```

### OpenAI Retries

```python
from openai import RateLimitError as OpenAIRateLimitError


def get_embedding_with_retry(text: str, max_retries: int = 3) -> list[float]:
    """Get embedding with retry logic."""

    for attempt in range(max_retries):
        try:
            response = openai_client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding

        except OpenAIRateLimitError:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) * 2
                time.sleep(wait)
            else:
                raise
```

### Database Transaction Handling

```python
def process_document_safely(doc, chunks, file_path):
    """Process with proper transaction handling."""

    try:
        with get_db_cursor(commit=True) as cursor:
            source_id = store_document(cursor, doc, chunks, file_path)
            process_chunks_for_concepts(cursor, source_id, chunks)
            source_level_relationship_pass(cursor, source_id)
            create_covers_edges(cursor, source_id)

            cursor.execute(
                "UPDATE sources SET status = 'COMPLETE' WHERE id = ?",
                (source_id,)
            )

    except Exception as e:
        # Transaction automatically rolled back by context manager
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("""
                UPDATE sources
                SET status = 'EXTRACT_FAILED', error_message = ?
                WHERE file_path = ?
            """, (str(e), file_path))
        raise
```

---

## Complete Pipeline Function

```python
# functions/function_app.py

@app.blob_trigger(arg_name="blob", path="documents/{name}", connection="AzureWebJobsStorage")
def ingest_document(blob: func.InputStream) -> None:
    """Complete ingestion pipeline."""

    filename = blob.name
    content = blob.read()

    try:
        # Step 1: Parse
        doc = parse_pdf(content, filename)

        # Step 2: Chunk
        chunks = chunk_document(doc, max_chunk_size=2000, overlap=200)

        # Step 3: Generate embeddings
        chunks = embed_chunks(chunks)

        # Step 4-6: Store and extract (with transaction)
        with get_db_cursor(commit=True) as cursor:
            # Store document and chunks
            source_id = store_document(cursor, doc, chunks, filename)

            # Extract concepts from each chunk
            process_chunks_for_concepts(cursor, source_id, chunks)

            # Source-level relationship pass
            source_level_relationship_pass(cursor, source_id)

            # Create covers edges
            create_covers_edges(cursor, source_id)

            # Mark complete
            cursor.execute(
                "UPDATE sources SET status = 'COMPLETE' WHERE id = ?",
                (source_id,)
            )

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
```
