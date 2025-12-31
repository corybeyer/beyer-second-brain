#!/usr/bin/env python3
"""Initialize the Second Brain database schema.

Schema will be created after document parsing exploration.
This script currently serves as a placeholder and connection test.
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.db.connection import get_db_cursor


def test_connection() -> bool:
    """Test database connection works."""
    print("Testing Azure SQL connection...")
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT @@VERSION;")
            version = cursor.fetchone()[0]
            print(f"  + Connected: {version[:50]}...")
            return True
    except Exception as e:
        print(f"  - Connection failed: {e}")
        return False


def init_database() -> None:
    """Initialize database schema.

    Currently a placeholder - schema will be defined after
    document parsing exploration determines data structure needs.
    """
    print("=" * 50)
    print("Second Brain Database Initialization")
    print("=" * 50)
    print()

    if not test_connection():
        print("\nFix connection issues before proceeding.")
        sys.exit(1)

    print()
    print("Schema creation is deferred until after document parsing.")
    print("The schema will use Azure SQL Graph with NODE/EDGE tables.")
    print()
    print("Planned tables:")
    print("  NODE: sources, chunks, concepts")
    print("  EDGE: covers, mentions, related_to, from_source")
    print()
    print("Next steps:")
    print("  1. Implement document parsing in functions/")
    print("  2. Explore parsed document structure")
    print("  3. Define schema based on actual data needs")
    print("  4. Update this script to create tables")


if __name__ == "__main__":
    try:
        init_database()
    except Exception as e:
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("  1. Check your .env file has correct Azure SQL credentials")
        print("  2. Ensure your IP is allowed in SQL Server firewall")
        print("  3. Run: python scripts/test_connectivity.py")
        sys.exit(1)
