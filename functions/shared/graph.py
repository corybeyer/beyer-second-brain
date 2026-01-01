"""Graph storage for concepts and relationships.

Stores extracted concepts and edges in Azure SQL Graph tables.
Handles upserts, mentions edges, and relationship edges.
"""

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Add project root for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.db.connection import get_db_cursor

from .concepts import ExtractionResult, Relationship, find_source_relationships
from .logging_utils import structured_logger

if TYPE_CHECKING:
    from .chunker import Chunk


def store_chunk_extraction(
    cursor,
    chunk_id: int,
    source_id: int,
    extraction: ExtractionResult,
) -> tuple[int, int]:
    """Store extracted concepts and create graph edges.

    Upserts concepts (by name) and creates edges:
    - mentions: chunk → concept
    - related_to: concept → concept (from same chunk)

    Args:
        cursor: Database cursor (caller manages transaction)
        chunk_id: ID of the chunk
        source_id: ID of the source document
        extraction: Concepts and relationships from Claude

    Returns:
        Tuple of (concepts_created, edges_created)
    """
    concepts_created = 0
    edges_created = 0

    # === UPSERT CONCEPTS ===
    for concept in extraction["concepts"]:
        cursor.execute(
            """
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
            """,
            (concept["name"], concept["category"], concept["description"]),
        )
        # MERGE doesn't reliably return rowcount for inserts vs updates
        concepts_created += 1

    # === CREATE mentions EDGES (chunk → concept) ===
    for concept in extraction["concepts"]:
        # Get first 200 chars of chunk as context
        cursor.execute(
            "SELECT LEFT(text, 200) FROM chunks WHERE id = ?",
            (chunk_id,),
        )
        row = cursor.fetchone()
        context = row[0] if row else ""

        cursor.execute(
            """
            INSERT INTO mentions ($from_id, $to_id, relevance, context)
            SELECT c.$node_id, con.$node_id, 0.8, ?
            FROM chunks c, concepts con
            WHERE c.id = ? AND LOWER(con.name) = LOWER(?)
              AND NOT EXISTS (
                  SELECT 1 FROM mentions m
                  WHERE m.$from_id = c.$node_id AND m.$to_id = con.$node_id
              )
            """,
            (context, chunk_id, concept["name"]),
        )
        edges_created += cursor.rowcount

    # === CREATE related_to EDGES (concept → concept) from within-chunk relationships ===
    for rel in extraction["relationships"]:
        cursor.execute(
            """
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
            """,
            (
                rel["type"],
                source_id,
                rel["from_concept"],
                rel["to_concept"],
                rel["type"],
            ),
        )
        edges_created += cursor.rowcount

    return concepts_created, edges_created


def source_level_relationship_pass(cursor, source_id: int) -> int:
    """Find relationships between all concepts in a source.

    Called after all chunks have been processed. Queries all concepts
    mentioned in the source and asks Claude to identify relationships.

    Args:
        cursor: Database cursor
        source_id: ID of the source to process

    Returns:
        Number of new relationships created
    """
    # Get all concepts mentioned in this source
    cursor.execute(
        """
        SELECT DISTINCT con.name, con.category, con.description
        FROM chunks c
        JOIN mentions m ON m.$from_id = c.$node_id
        JOIN concepts con ON m.$to_id = con.$node_id
        WHERE c.source_id = ?
        ORDER BY con.name
        """,
        (source_id,),
    )

    concepts = [
        {"name": row[0], "category": row[1], "description": row[2]}
        for row in cursor.fetchall()
    ]

    if len(concepts) < 2:
        structured_logger.info(
            "graph",
            "Skipping source-level pass (fewer than 2 concepts)",
            source_id=source_id,
            concept_count=len(concepts),
        )
        return 0

    structured_logger.info(
        "graph",
        "Running source-level relationship pass",
        source_id=source_id,
        concept_count=len(concepts),
    )

    # Ask Claude to identify relationships
    relationships = find_source_relationships(concepts)

    # Store new relationships
    created = 0
    for rel in relationships:
        cursor.execute(
            """
            INSERT INTO related_to ($from_id, $to_id, relationship_type, strength, source_id)
            SELECT c1.$node_id, c2.$node_id, ?, 0.7, ?
            FROM concepts c1, concepts c2
            WHERE LOWER(c1.name) = LOWER(?)
              AND LOWER(c2.name) = LOWER(?)
              AND NOT EXISTS (
                  SELECT 1 FROM related_to r
                  WHERE r.$from_id = c1.$node_id AND r.$to_id = c2.$node_id
              )
            """,
            (rel["type"], source_id, rel["from_concept"], rel["to_concept"]),
        )
        if cursor.rowcount > 0:
            created += 1

    structured_logger.info(
        "graph",
        "Source-level relationships created",
        source_id=source_id,
        relationships_created=created,
    )

    return created


def create_covers_edges(cursor, source_id: int) -> int:
    """Create covers edges showing which concepts a source discusses.

    Aggregates mention counts to create source → concept edges.

    Args:
        cursor: Database cursor
        source_id: ID of the source

    Returns:
        Number of covers edges created
    """
    # Get total chunk count for weight calculation
    cursor.execute(
        "SELECT COUNT(*) FROM chunks WHERE source_id = ?",
        (source_id,),
    )
    total_chunks = cursor.fetchone()[0]

    if total_chunks == 0:
        return 0

    # Create covers edges with weight based on mention frequency
    cursor.execute(
        """
        INSERT INTO covers ($from_id, $to_id, weight, mention_count)
        SELECT
            s.$node_id,
            con.$node_id,
            CAST(COUNT(DISTINCT c.id) AS FLOAT) / ?,
            COUNT(DISTINCT c.id)
        FROM sources s
        JOIN chunks c ON c.source_id = s.id
        JOIN mentions m ON m.$from_id = c.$node_id
        JOIN concepts con ON m.$to_id = con.$node_id
        WHERE s.id = ?
        GROUP BY s.$node_id, con.$node_id
        """,
        (total_chunks, source_id),
    )

    created = cursor.rowcount

    structured_logger.info(
        "graph",
        "Covers edges created",
        source_id=source_id,
        edges_created=created,
    )

    return created


def process_source_concepts(
    source_id: int,
    chunks: list["Chunk"],
) -> dict:
    """Process all chunks in a source for concept extraction.

    This is the main entry point for Phase 3 processing:
    1. Update source status to EXTRACTING
    2. Extract concepts from each chunk
    3. Run source-level relationship pass
    4. Create covers edges
    5. Update source status to COMPLETE

    Args:
        source_id: ID of the source
        chunks: List of Chunk objects (must have id set)

    Returns:
        Dict with processing statistics
    """
    from .concepts import extract_concepts_from_chunk

    stats = {
        "chunks_processed": 0,
        "concepts_extracted": 0,
        "relationships_created": 0,
        "errors": 0,
    }

    with get_db_cursor(commit=True) as cursor:
        # Update status to EXTRACTING
        cursor.execute(
            "UPDATE sources SET status = 'EXTRACTING', updated_at = GETDATE() WHERE id = ?",
            (source_id,),
        )

        # Process each chunk
        for chunk in chunks:
            if chunk.id is None:
                structured_logger.warning(
                    "graph",
                    "Chunk missing ID, skipping",
                    position=chunk.position,
                )
                continue

            try:
                extraction = extract_concepts_from_chunk(chunk.text)
                concepts_count, edges_count = store_chunk_extraction(
                    cursor, chunk.id, source_id, extraction
                )
                stats["chunks_processed"] += 1
                stats["concepts_extracted"] += concepts_count
                stats["relationships_created"] += edges_count

            except Exception as e:
                structured_logger.warning(
                    "graph",
                    f"Concept extraction failed for chunk: {e}",
                    chunk_id=chunk.id,
                    error_type=type(e).__name__,
                )
                stats["errors"] += 1
                continue

        # Source-level relationship pass
        try:
            source_rels = source_level_relationship_pass(cursor, source_id)
            stats["relationships_created"] += source_rels
        except Exception as e:
            structured_logger.warning(
                "graph",
                f"Source-level pass failed: {e}",
                source_id=source_id,
            )

        # Create covers edges
        try:
            covers_count = create_covers_edges(cursor, source_id)
            stats["relationships_created"] += covers_count
        except Exception as e:
            structured_logger.warning(
                "graph",
                f"Covers edges failed: {e}",
                source_id=source_id,
            )

        # Update status to COMPLETE
        cursor.execute(
            "UPDATE sources SET status = 'COMPLETE', updated_at = GETDATE() WHERE id = ?",
            (source_id,),
        )

    structured_logger.info(
        "graph",
        "Concept extraction complete",
        source_id=source_id,
        stats=stats,
    )

    return stats
