"""Database schema for Second Brain (Azure SQL with SQL Graph).

Schema will be finalized after document parsing exploration.
SQL Graph uses NODE and EDGE tables with MATCH syntax for graph queries.

Planned structure:
- NODE tables: sources, chunks, concepts
- EDGE tables: covers, mentions, related_to, from_source

Example SQL Graph syntax:
    CREATE TABLE concepts (
        id INT PRIMARY KEY IDENTITY,
        name NVARCHAR(255),
        description NVARCHAR(MAX)
    ) AS NODE;

    CREATE TABLE related_to AS EDGE;

    -- Query with MATCH
    SELECT c1.name, c2.name
    FROM concepts c1, related_to r, concepts c2
    WHERE MATCH(c1-(r)->c2);
"""

# Schema will be defined here after document parsing exploration
# For now, this module serves as documentation of the planned approach

SCHEMA_SQL = """
-- Schema placeholder
-- Will be populated after document parsing exploration
-- Azure SQL Graph tables will use AS NODE and AS EDGE syntax
"""
