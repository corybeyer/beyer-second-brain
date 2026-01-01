#!/usr/bin/env python3
"""Test connectivity to Azure resources for Second Brain."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def test_azure_sql() -> bool:
    """Test Azure SQL Database connection."""
    print("Testing Azure SQL connection...")

    try:
        import pyodbc

        server = os.environ["AZURE_SQL_SERVER"]
        database = os.environ.get("AZURE_SQL_DATABASE", "secondbrain")
        username = os.environ["AZURE_SQL_USERNAME"]
        password = os.environ["AZURE_SQL_PASSWORD"]

        conn_str = (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server=tcp:{server},1433;"
            f"Database={database};"
            f"Uid={username};"
            f"Pwd={password};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
        )

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Test basic query
        cursor.execute("SELECT @@VERSION;")
        version = cursor.fetchone()[0]
        print("  + Connected to Azure SQL")
        print(f"    Version: {version[:60]}...")

        # Test SQL Graph support (it's built-in to Azure SQL)
        cursor.execute("""
            SELECT CASE
                WHEN SERVERPROPERTY('EngineEdition') IN (5, 6, 8)
                THEN 1 ELSE 0 END AS IsAzureSQL;
        """)
        is_azure = cursor.fetchone()[0]
        if is_azure:
            print("  + Azure SQL detected (SQL Graph supported)")
        else:
            print("  - Not Azure SQL, SQL Graph may not be available")

        cursor.close()
        conn.close()
        return True

    except KeyError as e:
        print(f"  - Missing environment variable: {e}")
        print("    Check your .env file")
        return False
    except Exception as e:
        print(f"  - Connection failed: {e}")
        return False


def test_blob_storage() -> bool:
    """Test Azure Blob Storage connection."""
    print("\nTesting Azure Blob Storage connection...")

    try:
        from azure.storage.blob import BlobServiceClient

        connection_string = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        container_name = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "documents")

        blob_service = BlobServiceClient.from_connection_string(connection_string)

        # List containers
        containers = list(blob_service.list_containers())
        print("  + Connected to Azure Blob Storage")
        print(f"    Containers: {[c['name'] for c in containers]}")

        # Check for documents container
        container_names = [c["name"] for c in containers]
        if container_name in container_names:
            print(f"  + Container '{container_name}' exists")

            # Count blobs
            container_client = blob_service.get_container_client(container_name)
            blobs = list(container_client.list_blobs())
            print(f"    Files: {len(blobs)}")
        else:
            print(f"  - Container '{container_name}' not found")
            print(f"    Create it in Azure Portal or update AZURE_STORAGE_CONTAINER_NAME")

        return True

    except KeyError as e:
        print(f"  - Missing environment variable: {e}")
        print("    Check your .env file")
        return False
    except Exception as e:
        print(f"  - Connection failed: {e}")
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
        print("! No .env file found")
        print("  Copy .env.example to .env and fill in your values")
        print()

    results.append(("Azure SQL", test_azure_sql()))
    results.append(("Blob Storage", test_blob_storage()))

    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)

    all_passed = True
    for name, passed in results:
        status = "+ PASS" if passed else "- FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed! Ready for document parsing.")
        print("\nNext steps:")
        print("  1. Upload documents to blob storage")
        print("  2. Implement document parsing in functions/")
    else:
        print("Some tests failed. Check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
