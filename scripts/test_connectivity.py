#!/usr/bin/env python3
"""Test connectivity to Azure resources for Second Brain."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def test_postgres() -> bool:
    """Test PostgreSQL connection."""
    print("Testing PostgreSQL connection...")

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["POSTGRES_HOST"],
            port=int(os.environ.get("POSTGRES_PORT", 5432)),
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            sslmode="require",
        )

        cursor = conn.cursor()

        # Test basic query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"  ✓ Connected to PostgreSQL")
        print(f"    Version: {version[:60]}...")

        # Test pgvector extension
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        if cursor.fetchone():
            print("  ✓ pgvector extension is enabled")
        else:
            print("  ✗ pgvector extension NOT enabled")
            print("    → Enable 'vector' in Azure Portal: Server parameters → azure.extensions")

        # Test AGE extension
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'age';")
        if cursor.fetchone():
            print("  ✓ Apache AGE extension is enabled")
        else:
            print("  ✗ Apache AGE extension NOT enabled")
            print("    → Enable 'age' in Azure Portal: Server parameters → azure.extensions")

        cursor.close()
        conn.close()
        return True

    except KeyError as e:
        print(f"  ✗ Missing environment variable: {e}")
        print("    → Check your .env file")
        return False
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return False


def test_blob_storage() -> bool:
    """Test Azure Blob Storage connection."""
    print("\nTesting Azure Blob Storage connection...")

    try:
        from azure.storage.blob import BlobServiceClient

        connection_string = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        container_name = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "books")

        blob_service = BlobServiceClient.from_connection_string(connection_string)

        # List containers
        containers = list(blob_service.list_containers())
        print(f"  ✓ Connected to Azure Blob Storage")
        print(f"    Containers: {[c['name'] for c in containers]}")

        # Check for books container
        container_names = [c["name"] for c in containers]
        if container_name in container_names:
            print(f"  ✓ Container '{container_name}' exists")

            # Count blobs
            container_client = blob_service.get_container_client(container_name)
            blobs = list(container_client.list_blobs())
            print(f"    Files: {len(blobs)}")
        else:
            print(f"  ✗ Container '{container_name}' not found")
            print(f"    → Create it in Azure Portal or update AZURE_STORAGE_CONTAINER_NAME")

        return True

    except KeyError as e:
        print(f"  ✗ Missing environment variable: {e}")
        print("    → Check your .env file")
        return False
    except Exception as e:
        print(f"  ✗ Connection failed: {e}")
        return False


def main() -> None:
    """Run all connectivity tests."""
    print("=" * 50)
    print("Second Brain Connectivity Test")
    print("=" * 50)
    print()

    results = []

    # Check .env file exists
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print("⚠ No .env file found")
        print("  → Copy .env.example to .env and fill in your values")
        print()

    results.append(("PostgreSQL", test_postgres()))
    results.append(("Blob Storage", test_blob_storage()))

    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed! Ready for Phase 2.")
        print("\nNext steps:")
        print("  1. Run: python scripts/init_db.py")
        print("  2. Upload PDFs to blob storage")
    else:
        print("Some tests failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
