"""Database storage for parsed documents.

Handles idempotent storage of sources and chunks to Azure SQL Graph.
Implements delete-and-replace pattern for reprocessing.
Supports optional embeddings storage.
"""

import json

from .db.connection import get_db_cursor

from .chunker import Chunk
from .logging_utils import structured_logger
from .parser import ParsedDocument


def store_document(
    doc: ParsedDocument,
    chunks: list[Chunk],
    file_path: str,
) -> int:
    """Store parsed document and chunks in database.

    Implements idempotency via delete-and-replace pattern:
    - If source with same file_path exists, delete it (cascades to chunks)
    - Insert new source and all chunks in single transaction

    Args:
        doc: Parsed document with metadata
        chunks: List of chunks from document
        file_path: Original blob path (used as unique key)

    Returns:
        source_id of the created record

    Raises:
        Exception: If database operation fails (transaction rolled back)
    """
    with get_db_cursor(commit=True) as cursor:
        # === IDEMPOTENCY: Delete existing source if present ===
        # CASCADE delete removes chunks automatically
        cursor.execute(
            "DELETE FROM sources WHERE file_path = ?",
            (file_path,)
        )
        deleted = cursor.rowcount
        if deleted > 0:
            structured_logger.info(
                "store",
                "Deleted existing source for reprocessing",
                file_path=file_path,
            )

        # === INSERT SOURCE ===
        # Determine source type from filename
        source_type = "pdf" if file_path.lower().endswith(".pdf") else "unknown"

        # Serialize metadata to JSON
        metadata_json = json.dumps(doc.metadata) if doc.metadata else None

        cursor.execute(
            """
            INSERT INTO sources (
                title, author, source_type, file_path,
                page_count, status, metadata
            )
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, 'PARSED', ?)
            """,
            (
                doc.title,
                doc.author,
                source_type,
                file_path,
                doc.page_count,
                metadata_json,
            )
        )
        source_id = cursor.fetchone()[0]

        structured_logger.info(
            "store",
            "Source record created",
            source_id=source_id,
            title=doc.title,
        )

        # === INSERT CHUNKS ===
        chunk_count = 0
        for chunk in chunks:
            # Build chunk metadata
            chunk_metadata = {
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
            }
            chunk_metadata_json = json.dumps(chunk_metadata)

            # Serialize embedding if present
            embedding_json = None
            embedding_status = "PENDING"
            if chunk.embedding is not None:
                embedding_json = json.dumps(chunk.embedding)
                embedding_status = "COMPLETE"

            # Store chunk with processing status
            # embedding_status: COMPLETE if embedding provided, else PENDING
            # concept_status: always PENDING (timer function handles extraction)
            cursor.execute(
                """
                INSERT INTO chunks (
                    source_id, text, position, page_start, page_end,
                    section, char_count, embedding, embedding_status,
                    concept_status, metadata
                )
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    source_id,
                    chunk.text,
                    chunk.position,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.section,
                    len(chunk.text),
                    embedding_json,
                    embedding_status,
                    chunk_metadata_json,
                ),
            )
            # Store the chunk ID for later use in concept extraction
            row = cursor.fetchone()
            if row:
                chunk.id = row[0]
            chunk_count += 1

        structured_logger.info(
            "store",
            "Chunks stored",
            source_id=source_id,
            chunk_count=chunk_count,
        )

        # === CREATE from_source EDGES ===
        # Connect each chunk to its source for graph queries
        cursor.execute(
            """
            INSERT INTO from_source ($from_id, $to_id)
            SELECT c.$node_id, s.$node_id
            FROM chunks c, sources s
            WHERE c.source_id = ? AND s.id = ?
            """,
            (source_id, source_id)
        )
        edge_count = cursor.rowcount

        structured_logger.info(
            "store",
            "Graph edges created",
            source_id=source_id,
            edge_count=edge_count,
        )

        return source_id


def update_source_status(
    source_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update source processing status.

    Args:
        source_id: ID of source to update
        status: New status value
        error_message: Optional error message for failed states
    """
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE sources
            SET status = ?, error_message = ?, updated_at = GETDATE()
            WHERE id = ?
            """,
            (status, error_message, source_id)
        )

        structured_logger.info(
            "store",
            "Source status updated",
            source_id=source_id,
            status=status,
        )


def get_source_by_path(file_path: str) -> dict | None:
    """Get source record by file path.

    Args:
        file_path: Blob path to look up

    Returns:
        Source record as dict, or None if not found
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT id, title, author, source_type, file_path,
                   page_count, status, error_message, created_at
            FROM sources
            WHERE file_path = ?
            """,
            (file_path,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "title": row[1],
                "author": row[2],
                "source_type": row[3],
                "file_path": row[4],
                "page_count": row[5],
                "status": row[6],
                "error_message": row[7],
                "created_at": row[8],
            }
        return None


def get_chunks_for_source(source_id: int) -> list[dict]:
    """Get all chunks for a source.

    Args:
        source_id: ID of source

    Returns:
        List of chunk records as dicts
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT id, position, page_start, page_end, section,
                   char_count, text
            FROM chunks
            WHERE source_id = ?
            ORDER BY position
            """,
            (source_id,)
        )
        return [
            {
                "id": row[0],
                "position": row[1],
                "page_start": row[2],
                "page_end": row[3],
                "section": row[4],
                "char_count": row[5],
                "text": row[6],
            }
            for row in cursor.fetchall()
        ]


def get_pending_embedding_chunks(limit: int = 500) -> list[dict]:
    """Get chunks that need embeddings generated.

    Args:
        limit: Maximum number of chunks to return (for batching)

    Returns:
        List of chunk records with id, source_id, and text
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT TOP (?) c.id, c.source_id, c.text, s.file_path
            FROM chunks c
            JOIN sources s ON c.source_id = s.id
            WHERE c.embedding_status = 'PENDING'
            ORDER BY c.source_id, c.position
            """,
            (limit,)
        )
        return [
            {
                "id": row[0],
                "source_id": row[1],
                "text": row[2],
                "file_path": row[3],
            }
            for row in cursor.fetchall()
        ]


def update_chunk_embedding(
    chunk_id: int,
    embedding: list[float],
    status: str = "COMPLETE",
) -> None:
    """Update a chunk with its embedding and status.

    Args:
        chunk_id: ID of chunk to update
        embedding: Embedding vector (1536 floats)
        status: New embedding_status value
    """
    embedding_json = json.dumps(embedding)
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE chunks
            SET embedding = ?, embedding_status = ?
            WHERE id = ?
            """,
            (embedding_json, status, chunk_id)
        )


def update_chunk_embedding_failed(
    chunk_id: int,
    error_message: str,
) -> None:
    """Mark a chunk's embedding as failed.

    Args:
        chunk_id: ID of chunk
        error_message: Error description
    """
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE chunks
            SET embedding_status = 'FAILED',
                extraction_error = ?,
                extraction_attempts = extraction_attempts + 1
            WHERE id = ?
            """,
            (error_message[:500], chunk_id)  # Truncate to column size
        )


def get_pending_concept_chunks(limit: int = 200) -> list[dict]:
    """Get chunks that need concept extraction.

    Only returns chunks that have embeddings completed (prerequisite).

    Args:
        limit: Maximum number of chunks to return (for batching)

    Returns:
        List of chunk records with id, source_id, and text
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT TOP (?) c.id, c.source_id, c.text, s.file_path
            FROM chunks c
            JOIN sources s ON c.source_id = s.id
            WHERE c.embedding_status = 'COMPLETE'
              AND c.concept_status = 'PENDING'
              AND c.extraction_attempts < 3
            ORDER BY c.source_id, c.position
            """,
            (limit,)
        )
        return [
            {
                "id": row[0],
                "source_id": row[1],
                "text": row[2],
                "file_path": row[3],
            }
            for row in cursor.fetchall()
        ]


def update_chunk_concept_status(
    chunk_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update a chunk's concept extraction status.

    Args:
        chunk_id: ID of chunk to update
        status: New concept_status value ('EXTRACTED' or 'FAILED')
        error_message: Optional error message for failures
    """
    with get_db_cursor(commit=True) as cursor:
        if error_message:
            cursor.execute(
                """
                UPDATE chunks
                SET concept_status = ?,
                    extraction_error = ?,
                    extraction_attempts = extraction_attempts + 1
                WHERE id = ?
                """,
                (status, error_message[:500], chunk_id)
            )
        else:
            cursor.execute(
                """
                UPDATE chunks
                SET concept_status = ?
                WHERE id = ?
                """,
                (status, chunk_id)
            )


def check_source_complete(source_id: int) -> bool:
    """Check if all chunks for a source have completed processing.

    Args:
        source_id: ID of source to check

    Returns:
        True if all chunks have embedding_status='COMPLETE' and concept_status='EXTRACTED'
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN embedding_status = 'COMPLETE' THEN 1 ELSE 0 END) as embedded,
                SUM(CASE WHEN concept_status = 'EXTRACTED' THEN 1 ELSE 0 END) as extracted
            FROM chunks
            WHERE source_id = ?
            """,
            (source_id,)
        )
        row = cursor.fetchone()
        if row:
            total, embedded, extracted = row
            return total > 0 and total == embedded and total == extracted
        return False


def get_processing_stats() -> dict:
    """Get overall processing statistics.

    Returns:
        Dict with counts of pending, complete, failed chunks
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_chunks,
                SUM(CASE WHEN embedding_status = 'PENDING' THEN 1 ELSE 0 END) as pending_embeddings,
                SUM(CASE WHEN embedding_status = 'COMPLETE' THEN 1 ELSE 0 END) as complete_embeddings,
                SUM(CASE WHEN embedding_status = 'FAILED' THEN 1 ELSE 0 END) as failed_embeddings,
                SUM(CASE WHEN concept_status = 'PENDING' THEN 1 ELSE 0 END) as pending_concepts,
                SUM(CASE WHEN concept_status = 'EXTRACTED' THEN 1 ELSE 0 END) as extracted_concepts,
                SUM(CASE WHEN concept_status = 'FAILED' THEN 1 ELSE 0 END) as failed_concepts
            FROM chunks
            """
        )
        row = cursor.fetchone()
        if row:
            return {
                "total_chunks": row[0] or 0,
                "pending_embeddings": row[1] or 0,
                "complete_embeddings": row[2] or 0,
                "failed_embeddings": row[3] or 0,
                "pending_concepts": row[4] or 0,
                "extracted_concepts": row[5] or 0,
                "failed_concepts": row[6] or 0,
            }
        return {}
