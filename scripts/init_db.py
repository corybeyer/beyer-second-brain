#!/usr/bin/env python3
"""Initialize the Second Brain database with schema and extensions."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from db.connection import get_db_cursor
from db.models import SCHEMA_SQL, SEARCH_FUNCTIONS_SQL


def init_database() -> None:
    """Initialize database with extensions, tables, and functions."""
    print("Initializing Second Brain database...")

    # Split schema into individual statements for better error handling
    with get_db_cursor() as cursor:
        # Step 1: Enable extensions
        print("  Enabling pgvector extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        print("  Enabling Apache AGE extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS age;")

    # Step 2: Create tables (separate transaction for cleaner errors)
    with get_db_cursor() as cursor:
        print("  Creating tables...")

        # Books table
        cursor.execute("""
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
        """)

        # Chunks table
        cursor.execute("""
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
        """)

        # Concepts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS concepts (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                description TEXT,
                category VARCHAR(100),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # Junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunk_concepts (
                chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                concept_id INTEGER NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
                relevance_score FLOAT DEFAULT 1.0,
                PRIMARY KEY (chunk_id, concept_id)
            );
        """)

    # Step 3: Create indexes
    with get_db_cursor() as cursor:
        print("  Creating indexes...")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS chunks_embedding_idx
            ON chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS chunks_text_search_idx
            ON chunks USING gin(to_tsvector('english', text));
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS books_author_idx ON books(author);")
        cursor.execute("CREATE INDEX IF NOT EXISTS chunks_book_id_idx ON chunks(book_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS concepts_name_idx ON concepts(name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS concepts_category_idx ON concepts(category);")

    # Step 4: Create search functions
    with get_db_cursor() as cursor:
        print("  Creating search functions...")

        cursor.execute("""
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
        """)

        cursor.execute("""
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
        """)

    # Step 5: Set up Apache AGE graph
    with get_db_cursor() as cursor:
        print("  Setting up knowledge graph...")
        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, \"$user\", public;")

        # Check if graph exists before creating
        cursor.execute("""
            SELECT * FROM ag_catalog.ag_graph WHERE name = 'knowledge_graph';
        """)
        if cursor.fetchone() is None:
            cursor.execute("SELECT create_graph('knowledge_graph');")

    print("\nDatabase initialization complete!")
    print("\nCreated:")
    print("  - Tables: books, chunks, concepts, chunk_concepts")
    print("  - Extensions: vector, age")
    print("  - Indexes: embedding (IVFFlat), full-text search")
    print("  - Functions: semantic_search, keyword_search")
    print("  - Graph: knowledge_graph")


if __name__ == "__main__":
    try:
        init_database()
    except Exception as e:
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("  1. Check your .env file has correct connection details")
        print("  2. Ensure your IP is allowed in PostgreSQL firewall")
        print("  3. Verify extensions are enabled in Azure Portal")
        sys.exit(1)
