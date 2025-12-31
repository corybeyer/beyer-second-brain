"""Database models and schema for Second Brain."""

SCHEMA_SQL = """
-- Enable extensions (must be done by admin/superuser first)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

-- Load AGE
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Books table
CREATE TABLE IF NOT EXISTS books (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    author VARCHAR(255),
    file_path VARCHAR(1000) NOT NULL UNIQUE,
    file_hash VARCHAR(64),
    page_count INTEGER,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Chunks table (with vector embedding)
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter VARCHAR(255),
    section VARCHAR(255),
    text TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    chunk_index INTEGER NOT NULL,
    token_count INTEGER,
    embedding vector(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(book_id, chunk_index)
);

-- Concepts table (extracted topics/themes)
CREATE TABLE IF NOT EXISTS concepts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    category VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Junction table: which chunks mention which concepts
CREATE TABLE IF NOT EXISTS chunk_concepts (
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    concept_id INTEGER NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    relevance_score FLOAT DEFAULT 1.0,
    PRIMARY KEY (chunk_id, concept_id)
);

-- ============================================================================
-- Indexes
-- ============================================================================

-- Vector similarity search index (IVFFlat for better performance on larger datasets)
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
ON chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Full-text search on chunk content
CREATE INDEX IF NOT EXISTS chunks_text_search_idx
ON chunks USING gin(to_tsvector('english', text));

-- Book lookups
CREATE INDEX IF NOT EXISTS books_author_idx ON books(author);
CREATE INDEX IF NOT EXISTS chunks_book_id_idx ON chunks(book_id);

-- Concept lookups
CREATE INDEX IF NOT EXISTS concepts_name_idx ON concepts(name);
CREATE INDEX IF NOT EXISTS concepts_category_idx ON concepts(category);

-- ============================================================================
-- Graph Setup (Apache AGE)
-- ============================================================================

-- Create the knowledge graph
SELECT create_graph('knowledge_graph');

-- Graph will contain:
-- Vertices: Book, Concept, Chunk
-- Edges: COVERS (Book->Concept), MENTIONS (Chunk->Concept),
--        RELATED_TO (Concept->Concept), FROM (Chunk->Book)
"""

SEARCH_FUNCTIONS_SQL = """
-- ============================================================================
-- Search Functions
-- ============================================================================

-- Semantic search: find chunks similar to a query embedding
CREATE OR REPLACE FUNCTION semantic_search(
    query_embedding vector(1536),
    match_count INTEGER DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    chunk_id INTEGER,
    book_title VARCHAR,
    author VARCHAR,
    chapter VARCHAR,
    text TEXT,
    page_start INTEGER,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        b.title,
        b.author,
        c.chapter,
        c.text,
        c.page_start,
        1 - (c.embedding <=> query_embedding) as similarity
    FROM chunks c
    JOIN books b ON c.book_id = b.id
    WHERE c.embedding IS NOT NULL
    AND 1 - (c.embedding <=> query_embedding) > similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Full-text search on chunk content
CREATE OR REPLACE FUNCTION keyword_search(
    search_query TEXT,
    match_count INTEGER DEFAULT 10
)
RETURNS TABLE (
    chunk_id INTEGER,
    book_title VARCHAR,
    author VARCHAR,
    chapter VARCHAR,
    text TEXT,
    page_start INTEGER,
    rank FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id,
        b.title,
        b.author,
        c.chapter,
        c.text,
        c.page_start,
        ts_rank(to_tsvector('english', c.text), plainto_tsquery('english', search_query)) as rank
    FROM chunks c
    JOIN books b ON c.book_id = b.id
    WHERE to_tsvector('english', c.text) @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;
"""
