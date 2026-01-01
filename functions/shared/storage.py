"""Database storage for parsed documents.

Handles idempotent storage of sources and chunks to Azure SQL Graph.
Implements delete-and-replace pattern for reprocessing.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

# Add project root for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.db.connection import get_db_cursor

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

            cursor.execute(
                """
                INSERT INTO chunks (
                    source_id, text, position, page_start, page_end,
                    section, char_count, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    chunk.text,
                    chunk.position,
                    chunk.page_start,
                    chunk.page_end,
                    chunk.section,
                    len(chunk.text),
                    chunk_metadata_json,
                )
            )
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
