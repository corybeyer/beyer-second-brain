#!/usr/bin/env python3
"""Cross-source relationship pass.

Finds relationships between concepts that span multiple sources.
Run periodically after new sources are ingested.

Usage:
    python scripts/cross_source_pass.py          # Run once
    python scripts/cross_source_pass.py --dry-run  # Preview without changes
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic

from shared.db.connection import get_db_cursor

# Model configuration
EXTRACTION_MODEL = "claude-sonnet-4-20250514"

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


def get_shared_concepts(cursor) -> list[dict]:
    """Get concepts that appear in 2+ sources."""
    cursor.execute("""
        SELECT
            con.name,
            con.category,
            con.description,
            STRING_AGG(s.title, ' | ') as sources,
            COUNT(DISTINCT s.id) as source_count
        FROM concepts con
        JOIN covers cov ON cov.$to_id = con.$node_id
        JOIN sources s ON cov.$from_id = s.$node_id
        GROUP BY con.id, con.name, con.category, con.description
        HAVING COUNT(DISTINCT s.id) >= 2
        ORDER BY COUNT(DISTINCT s.id) DESC
    """)

    return [
        {
            "name": row[0],
            "category": row[1],
            "description": row[2],
            "sources": row[3],
            "source_count": row[4],
        }
        for row in cursor.fetchall()
    ]


def find_cross_source_relationships(
    concepts: list[dict],
    client: anthropic.Anthropic,
) -> list[dict]:
    """Ask Claude to identify cross-source relationships."""
    if len(concepts) < 2:
        return []

    concepts_with_sources = "\n".join([
        f"- {c['name']} ({c['category']}): appears in [{c['sources']}]"
        for c in concepts
    ])

    prompt = CROSS_SOURCE_PROMPT.format(concepts_with_sources=concepts_with_sources)

    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    content = response.content[0].text
    return json.loads(content)


def store_relationships(cursor, relationships: list[dict], dry_run: bool = False) -> int:
    """Store cross-source relationships in database."""
    created = 0

    for rel in relationships:
        if dry_run:
            print(f"  Would create: {rel['from']} --[{rel['type']}]--> {rel['to']}")
            print(f"    Reason: {rel.get('reason', 'N/A')}")
            created += 1
            continue

        cursor.execute("""
            INSERT INTO related_to ($from_id, $to_id, relationship_type, strength, source_id)
            SELECT c1.$node_id, c2.$node_id, ?, 0.6, NULL
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
            print(f"  Created: {rel['from']} --[{rel['type']}]--> {rel['to']}")

    return created


def main():
    parser = argparse.ArgumentParser(
        description="Find relationships between concepts across sources"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview relationships without storing",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("Cross-Source Relationship Pass")
    print("=" * 55)
    print()

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Get shared concepts
    print("Finding concepts shared across sources...")
    with get_db_cursor() as cursor:
        concepts = get_shared_concepts(cursor)

    print(f"  Found {len(concepts)} concepts in 2+ sources")

    if len(concepts) < 2:
        print("\nNot enough shared concepts for relationship analysis.")
        return

    # Preview concepts
    print("\nShared concepts:")
    for c in concepts[:10]:
        print(f"  - {c['name']} ({c['source_count']} sources)")
    if len(concepts) > 10:
        print(f"  ... and {len(concepts) - 10} more")
    print()

    # Find relationships
    print("Analyzing relationships with Claude...")
    try:
        relationships = find_cross_source_relationships(concepts, client)
    except json.JSONDecodeError as e:
        print(f"  Error parsing response: {e}")
        sys.exit(1)

    print(f"  Found {len(relationships)} potential relationships")
    print()

    if not relationships:
        print("No new relationships identified.")
        return

    # Store relationships
    mode = "Preview" if args.dry_run else "Creating"
    print(f"{mode} relationships...")

    with get_db_cursor(commit=not args.dry_run) as cursor:
        created = store_relationships(cursor, relationships, dry_run=args.dry_run)

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
