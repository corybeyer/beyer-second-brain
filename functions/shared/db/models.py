"""Database schema for Second Brain (Azure SQL with SQL Graph).

Defines NODE and EDGE tables for document storage and concept relationships.
Uses SQL Graph syntax with MATCH queries for graph traversal.

Tables:
    NODE: sources, chunks, concepts
    EDGE: from_source, covers, mentions, related_to
"""

# Processing states for document lifecycle
PROCESSING_STATES = [
    "UPLOADED",      # Blob detected, not yet processed
    "PARSING",       # Currently being parsed
    "PARSED",        # Parsed and chunked, awaiting concept extraction
    "EXTRACTING",    # Claude API extracting concepts
    "COMPLETE",      # Fully processed
    "PARSE_FAILED",  # Parsing failed
    "EXTRACT_FAILED",  # Concept extraction failed
]

# SQL Schema for Azure SQL Graph
SCHEMA_SQL = """
-- =============================================
-- NODE TABLES
-- =============================================

-- Sources: PDFs, markdown files, articles
-- Tracks processing status for recovery and idempotency
CREATE TABLE sources (
    id INT PRIMARY KEY IDENTITY(1,1),
    title NVARCHAR(500),
    author NVARCHAR(255),
    source_type NVARCHAR(50) NOT NULL,  -- 'pdf', 'markdown', 'article'
    file_path NVARCHAR(500) NOT NULL,   -- Unique identifier for idempotency
    page_count INT,
    status NVARCHAR(50) NOT NULL DEFAULT 'UPLOADED',
    error_message NVARCHAR(MAX),
    metadata NVARCHAR(MAX),             -- JSON for type-specific fields
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    CONSTRAINT UQ_sources_file_path UNIQUE (file_path),
    CONSTRAINT CK_sources_status CHECK (status IN (
        'UPLOADED', 'PARSING', 'PARSED', 'EXTRACTING',
        'COMPLETE', 'PARSE_FAILED', 'EXTRACT_FAILED'
    ))
) AS NODE;

-- Chunks: text segments from sources
-- Position is sequential within each source (invariant)
CREATE TABLE chunks (
    id INT PRIMARY KEY IDENTITY(1,1),
    source_id INT NOT NULL,
    text NVARCHAR(MAX) NOT NULL,
    position INT NOT NULL,              -- Sequential ordering within source
    page_start INT,
    page_end INT,
    section NVARCHAR(500),              -- Heading or chapter name
    char_count INT NOT NULL,            -- For cost tracking
    embedding VECTOR(1536),             -- OpenAI text-embedding-3-small
    metadata NVARCHAR(MAX),             -- JSON for additional fields
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_chunks_source FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    CONSTRAINT UQ_chunks_position UNIQUE (source_id, position),
    CONSTRAINT CK_chunks_text_not_empty CHECK (LEN(text) > 0)
) AS NODE;

-- Concepts: extracted topics and ideas (Phase 3)
-- Names are unique (case-insensitive) for upsert pattern
CREATE TABLE concepts (
    id INT PRIMARY KEY IDENTITY(1,1),
    name NVARCHAR(255) NOT NULL,
    description NVARCHAR(MAX),
    category NVARCHAR(100),             -- 'methodology', 'principle', 'tool', etc.
    embedding VECTOR(1536),             -- For concept similarity search
    created_at DATETIME2 NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME2 NOT NULL DEFAULT GETDATE()
) AS NODE;

-- Case-insensitive unique index on concept name
CREATE UNIQUE INDEX UQ_concepts_name_ci
ON concepts (name)
WHERE name IS NOT NULL;

-- =============================================
-- EDGE TABLES
-- =============================================

-- from_source: Chunk belongs to Source
-- Redundant with FK but enables graph queries
CREATE TABLE from_source AS EDGE;

-- covers: Source covers Concept (document-level relationship)
CREATE TABLE covers (
    weight FLOAT DEFAULT 1.0,           -- Relevance/prominence (0-1)
    mention_count INT DEFAULT 1         -- How many times concept appears
) AS EDGE;

-- mentions: Chunk mentions Concept (granular relationship)
CREATE TABLE mentions (
    relevance FLOAT DEFAULT 1.0,        -- How central to the chunk (0-1)
    context NVARCHAR(500)               -- Surrounding text snippet
) AS EDGE;

-- related_to: Concept related to Concept
CREATE TABLE related_to (
    relationship_type NVARCHAR(100),    -- 'similar_to', 'part_of', 'enables', etc.
    strength FLOAT DEFAULT 1.0,         -- Relationship strength (0-1)
    source_id INT                       -- Which source established this relationship
) AS EDGE;

-- =============================================
-- INDEXES FOR PERFORMANCE
-- =============================================

-- Sources: query by status for processing queue
CREATE INDEX IX_sources_status ON sources(status);

-- Sources: query by type for filtering
CREATE INDEX IX_sources_type ON sources(source_type);

-- Chunks: query by source for retrieval
CREATE INDEX IX_chunks_source ON chunks(source_id);

-- Concepts: query by category for browsing
CREATE INDEX IX_concepts_category ON concepts(category);
"""

# Drop all tables (for clean reset during development)
DROP_SCHEMA_SQL = """
-- Drop edges first (they reference nodes)
IF OBJECT_ID('dbo.related_to', 'U') IS NOT NULL DROP TABLE related_to;
IF OBJECT_ID('dbo.mentions', 'U') IS NOT NULL DROP TABLE mentions;
IF OBJECT_ID('dbo.covers', 'U') IS NOT NULL DROP TABLE covers;
IF OBJECT_ID('dbo.from_source', 'U') IS NOT NULL DROP TABLE from_source;

-- Drop nodes (chunks before sources due to FK)
IF OBJECT_ID('dbo.concepts', 'U') IS NOT NULL DROP TABLE concepts;
IF OBJECT_ID('dbo.chunks', 'U') IS NOT NULL DROP TABLE chunks;
IF OBJECT_ID('dbo.sources', 'U') IS NOT NULL DROP TABLE sources;
"""

# Check if schema exists
CHECK_SCHEMA_SQL = """
SELECT COUNT(*)
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME IN ('sources', 'chunks', 'concepts');
"""
