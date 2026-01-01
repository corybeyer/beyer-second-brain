#!/usr/bin/env python3
"""Initialize the Second Brain database schema.

Creates Azure SQL Graph tables for sources, chunks, concepts, and relationships.
Supports both fresh install and reset (drop + recreate).

Usage:
    python scripts/init_db.py          # Create tables if not exist
    python scripts/init_db.py --reset  # Drop and recreate all tables
    python scripts/init_db.py --check  # Check schema status only
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.db.connection import get_db_cursor
from shared.db.models import SCHEMA_SQL, DROP_SCHEMA_SQL, CHECK_SCHEMA_SQL


def check_connection() -> bool:
    """Test database connection works."""
    print("Testing Azure SQL connection...")
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT @@VERSION;")
            version = cursor.fetchone()[0]
            print(f"  Connected: {version[:60]}...")
            return True
    except Exception as e:
        print(f"  Connection failed: {e}")
        return False


def check_schema() -> dict:
    """Check current schema status.

    Returns:
        dict with 'exists' (bool) and 'tables' (list of existing table names)
    """
    print("Checking schema status...")
    try:
        with get_db_cursor() as cursor:
            # Check for NODE/EDGE tables
            cursor.execute("""
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'dbo'
                  AND TABLE_NAME IN ('sources', 'chunks', 'concepts',
                                     'from_source', 'covers', 'mentions', 'related_to')
            """)
            tables = [row[0] for row in cursor.fetchall()]

            if tables:
                print(f"  Found tables: {', '.join(tables)}")
            else:
                print("  No schema tables found")

            return {
                "exists": len(tables) > 0,
                "tables": tables,
                "complete": len(tables) == 7,  # 3 nodes + 4 edges
            }
    except Exception as e:
        print(f"  Schema check failed: {e}")
        return {"exists": False, "tables": [], "complete": False}


def drop_schema() -> bool:
    """Drop all schema tables."""
    print("Dropping existing schema...")
    try:
        with get_db_cursor(commit=True) as cursor:
            # Execute each DROP statement separately
            for statement in DROP_SCHEMA_SQL.strip().split(";"):
                statement = statement.strip()
                if statement and not statement.startswith("--"):
                    cursor.execute(statement)
            print("  Schema dropped")
            return True
    except Exception as e:
        print(f"  Drop failed: {e}")
        return False


def create_schema() -> bool:
    """Create all schema tables."""
    print("Creating schema tables...")
    try:
        with get_db_cursor(commit=True) as cursor:
            # Split and execute each CREATE statement separately
            # Azure SQL doesn't support multiple statements in one execute
            statements = []
            current = []

            for line in SCHEMA_SQL.split("\n"):
                # Skip pure comment lines but keep inline comments
                if line.strip().startswith("--"):
                    continue
                current.append(line)
                if ";" in line:
                    statements.append("\n".join(current))
                    current = []

            for i, statement in enumerate(statements, 1):
                statement = statement.strip()
                if statement:
                    try:
                        cursor.execute(statement)
                    except Exception as e:
                        # Extract table/index name for better error message
                        if "CREATE TABLE" in statement:
                            name = statement.split("CREATE TABLE")[1].split("(")[0].strip()
                            print(f"  Failed creating table {name}: {e}")
                        elif "CREATE" in statement and "INDEX" in statement:
                            name = statement.split("INDEX")[1].split("ON")[0].strip()
                            print(f"  Failed creating index {name}: {e}")
                        else:
                            print(f"  Failed statement {i}: {e}")
                        raise

            print("  Schema created successfully")
            return True
    except Exception as e:
        print(f"  Schema creation failed: {e}")
        return False


def verify_schema() -> bool:
    """Verify schema was created correctly."""
    print("Verifying schema...")
    status = check_schema()
    if status["complete"]:
        print("  All 7 tables created (3 nodes, 4 edges)")
        return True
    else:
        print(f"  Incomplete: only {len(status['tables'])} of 7 tables found")
        return False


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Initialize Second Brain database schema"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables (WARNING: destroys data)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check schema status only, don't modify",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("Second Brain Database Initialization")
    print("=" * 55)
    print()

    # Test connection first
    if not check_connection():
        print("\nFix connection issues before proceeding.")
        sys.exit(1)
    print()

    # Check current status
    status = check_schema()
    print()

    # Check-only mode
    if args.check:
        if status["complete"]:
            print("Schema is complete and ready.")
        elif status["exists"]:
            print("Schema is incomplete. Run without --check to finish setup.")
        else:
            print("No schema found. Run without --check to create.")
        return

    # Reset mode
    if args.reset:
        if status["exists"]:
            confirm = input("This will DELETE ALL DATA. Type 'yes' to confirm: ")
            if confirm.lower() != "yes":
                print("Aborted.")
                return
            if not drop_schema():
                sys.exit(1)
            print()

    # Create if needed
    if args.reset or not status["exists"]:
        if not create_schema():
            sys.exit(1)
        print()
        if not verify_schema():
            sys.exit(1)
    elif status["complete"]:
        print("Schema already exists and is complete.")
        print("Use --reset to drop and recreate.")
    else:
        print("Partial schema exists. Use --reset to clean up.")

    print()
    print("Done!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check your .env file has correct Azure SQL credentials")
        print("  2. Ensure your IP is allowed in SQL Server firewall")
        print("  3. Run: python scripts/test_connectivity.py")
        sys.exit(1)
