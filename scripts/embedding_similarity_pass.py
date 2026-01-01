#!/usr/bin/env python3
"""Embedding similarity pass.

Finds semantically similar concepts using embedding cosine similarity.
Creates similar_to edges for concept pairs above threshold.

Usage:
    python scripts/embedding_similarity_pass.py                    # Run with default threshold
    python scripts/embedding_similarity_pass.py --threshold 0.8    # Custom threshold
    python scripts/embedding_similarity_pass.py --dry-run          # Preview without changes
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from shared.db.connection import get_db_cursor

# Default similarity threshold
DEFAULT_THRESHOLD = 0.85


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def get_concepts_needing_embeddings(cursor) -> list[dict]:
    """Get concepts with descriptions but no embeddings."""
    cursor.execute("""
        SELECT id, name, description
        FROM concepts
        WHERE description IS NOT NULL
          AND embedding IS NULL
    """)

    return [
        {"id": row[0], "name": row[1], "description": row[2]}
        for row in cursor.fetchall()
    ]


def generate_concept_embeddings(
    cursor,
    concepts: list[dict],
    client: OpenAI,
) -> int:
    """Generate and store embeddings for concepts."""
    if not concepts:
        return 0

    texts = [f"{c['name']}: {c['description']}" for c in concepts]

    # Batch embedding generation
    response = client.embeddings.create(
        input=texts,
        model="text-embedding-3-small",
    )

    embeddings = [item.embedding for item in response.data]

    # Store embeddings
    for concept, embedding in zip(concepts, embeddings):
        embedding_json = json.dumps(embedding)
        cursor.execute("""
            UPDATE concepts
            SET embedding = CAST(? AS VECTOR(1536)), updated_at = GETDATE()
            WHERE id = ?
        """, (embedding_json, concept["id"]))

    return len(concepts)


def get_concepts_with_embeddings(cursor) -> list[dict]:
    """Get all concepts that have embeddings."""
    cursor.execute("""
        SELECT id, name, embedding
        FROM concepts
        WHERE embedding IS NOT NULL
    """)

    concepts = []
    for row in cursor.fetchall():
        # Parse embedding from database
        embedding = row[2]
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        elif hasattr(embedding, "__iter__"):
            embedding = list(embedding)

        concepts.append({
            "id": row[0],
            "name": row[1],
            "embedding": embedding,
        })

    return concepts


def find_similar_pairs(
    concepts: list[dict],
    threshold: float,
) -> list[tuple[dict, dict, float]]:
    """Find all concept pairs above similarity threshold."""
    similar = []

    for i, c1 in enumerate(concepts):
        for c2 in concepts[i + 1:]:
            similarity = cosine_similarity(c1["embedding"], c2["embedding"])
            if similarity >= threshold:
                similar.append((c1, c2, similarity))

    # Sort by similarity descending
    similar.sort(key=lambda x: x[2], reverse=True)

    return similar


def store_similar_relationships(
    cursor,
    pairs: list[tuple[dict, dict, float]],
    dry_run: bool = False,
) -> int:
    """Store similar_to edges for concept pairs."""
    created = 0

    for c1, c2, similarity in pairs:
        if dry_run:
            print(f"  Would create: {c1['name']} <--similar_to--> {c2['name']} ({similarity:.3f})")
            created += 1
            continue

        # Check if relationship already exists
        cursor.execute("""
            SELECT 1 FROM related_to r, concepts a, concepts b
            WHERE r.$from_id = a.$node_id AND r.$to_id = b.$node_id
              AND ((a.id = ? AND b.id = ?) OR (a.id = ? AND b.id = ?))
        """, (c1["id"], c2["id"], c2["id"], c1["id"]))

        if cursor.fetchone():
            continue

        # Create relationship
        cursor.execute("""
            INSERT INTO related_to ($from_id, $to_id, relationship_type, strength)
            SELECT a.$node_id, b.$node_id, 'similar_to', ?
            FROM concepts a, concepts b
            WHERE a.id = ? AND b.id = ?
        """, (similarity, c1["id"], c2["id"]))

        if cursor.rowcount > 0:
            created += 1
            print(f"  Created: {c1['name']} <--similar_to--> {c2['name']} ({similarity:.3f})")

    return created


def main():
    parser = argparse.ArgumentParser(
        description="Find semantically similar concepts via embeddings"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Similarity threshold (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview similar pairs without storing",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("Embedding Similarity Pass")
    print("=" * 55)
    print(f"Threshold: {args.threshold}")
    print()

    # Check for API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    # Step 1: Generate embeddings for concepts that don't have them
    print("Checking for concepts needing embeddings...")
    with get_db_cursor(commit=True) as cursor:
        concepts_to_embed = get_concepts_needing_embeddings(cursor)

        if concepts_to_embed:
            print(f"  Generating embeddings for {len(concepts_to_embed)} concepts...")
            embedded = generate_concept_embeddings(cursor, concepts_to_embed, client)
            print(f"  Generated {embedded} embeddings")
        else:
            print("  All concepts have embeddings")
    print()

    # Step 2: Get concepts with embeddings
    print("Loading concepts with embeddings...")
    with get_db_cursor() as cursor:
        concepts = get_concepts_with_embeddings(cursor)

    print(f"  Found {len(concepts)} concepts with embeddings")
    print()

    if len(concepts) < 2:
        print("Not enough concepts for similarity comparison.")
        return

    # Step 3: Find similar pairs
    print(f"Finding pairs with similarity >= {args.threshold}...")
    pairs = find_similar_pairs(concepts, args.threshold)
    print(f"  Found {len(pairs)} similar pairs")
    print()

    if not pairs:
        print("No similar concept pairs found above threshold.")
        return

    # Step 4: Store relationships
    mode = "Preview" if args.dry_run else "Creating"
    print(f"{mode} similar_to relationships...")

    with get_db_cursor(commit=not args.dry_run) as cursor:
        created = store_similar_relationships(cursor, pairs, dry_run=args.dry_run)

    print()
    print(f"{'Would create' if args.dry_run else 'Created'} {created} relationships")
    print("\nDone!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
