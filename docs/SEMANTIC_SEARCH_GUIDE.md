# Semantic Search Implementation Guide

This guide covers implementing semantic search for the Second Brain project using Azure SQL Database's native vector support.

---

## Important: Two Approaches (Only One Works for Us)

### ❌ SQL Server Statistical Semantic Search (NOT available)

The traditional `STATISTICAL_SEMANTICS` feature with `SEMANTICKEYPHRASETABLE`, `SEMANTICSIMILARITYTABLE`, etc. is **NOT supported in Azure SQL Database**. It only works with:
- SQL Server on-premises (2012+)
- SQL Server on Azure VMs

Since we're using Azure SQL Database, this approach won't work.

### ✅ Azure SQL Database Vector Support (Our Approach)

Azure SQL Database now has native vector support (Public Preview, Nov 2024):
- `VECTOR` data type (up to 1998 dimensions)
- `VECTOR_DISTANCE` function for similarity calculations
- `sp_invoke_external_rest_endpoint` to call embedding APIs directly from SQL

---

## Architecture Overview

```
Document Upload → Parse → Chunk → Generate Embeddings → Store in Azure SQL
                                        ↓
                              OpenAI/Azure OpenAI API

User Query → Generate Query Embedding → VECTOR_DISTANCE search → Return Top-K chunks
```

---

## Step 1: Update Schema for Vectors

Add embedding column to chunks table:

```sql
-- Add vector column to chunks table
-- OpenAI text-embedding-3-small uses 1536 dimensions
ALTER TABLE chunks ADD embedding VECTOR(1536);

-- Create index for faster similarity search (optional, helps with large datasets)
-- Note: DiskANN indexing is SQL Server 2025 only, not yet in Azure SQL Database
-- For now, brute-force similarity search works for <10K chunks
```

---

## Step 2: Configure Azure OpenAI (or OpenAI)

### Option A: Azure OpenAI (Recommended for Azure integration)

1. Create Azure OpenAI resource in Azure Portal
2. Deploy `text-embedding-3-small` model (or `text-embedding-ada-002`)
3. Get the endpoint URL and API key
4. Store in Function App environment variables:
   - `AZURE_OPENAI_ENDPOINT`
   - `AZURE_OPENAI_API_KEY`
   - `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` (deployment name)

### Option B: OpenAI API

1. Get API key from OpenAI
2. Store in Function App environment variables:
   - `OPENAI_API_KEY`

---

## Step 3: Generate Embeddings in Python

### Using OpenAI Python SDK

```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Generate embedding vector for text.

    Args:
        text: Text to embed (max ~8000 tokens for text-embedding-3-small)
        model: Embedding model to use

    Returns:
        List of floats (1536 dimensions for text-embedding-3-small)
    """
    response = client.embeddings.create(
        input=text,
        model=model
    )
    return response.data[0].embedding
```

### Using Azure OpenAI

```python
from openai import AzureOpenAI
import os

client = AzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2024-02-01",
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
)

def get_embedding(text: str) -> list[float]:
    """Generate embedding using Azure OpenAI."""
    deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
    response = client.embeddings.create(
        input=text,
        model=deployment
    )
    return response.data[0].embedding
```

---

## Step 4: Store Embeddings in Azure SQL

### Python code to store embedding

```python
import json

def store_chunk_with_embedding(cursor, chunk_id: int, embedding: list[float]):
    """Update chunk with its embedding vector.

    Args:
        cursor: Database cursor
        chunk_id: ID of chunk to update
        embedding: List of floats (embedding vector)
    """
    # Convert to JSON array format for VECTOR type
    embedding_json = json.dumps(embedding)

    cursor.execute(
        """
        UPDATE chunks
        SET embedding = CAST(? AS VECTOR(1536))
        WHERE id = ?
        """,
        (embedding_json, chunk_id)
    )
```

### Alternative: Call OpenAI directly from SQL

Azure SQL can call REST APIs directly using `sp_invoke_external_rest_endpoint`:

```sql
DECLARE @url NVARCHAR(4000) = N'https://api.openai.com/v1/embeddings';
DECLARE @headers NVARCHAR(4000) = N'{"Authorization": "Bearer YOUR_API_KEY"}';
DECLARE @payload NVARCHAR(MAX) = N'{
    "input": "Your text to embed here",
    "model": "text-embedding-3-small"
}';

DECLARE @response NVARCHAR(MAX);
DECLARE @ret INT;

EXEC @ret = sp_invoke_external_rest_endpoint
    @url = @url,
    @method = 'POST',
    @headers = @headers,
    @payload = @payload,
    @response = @response OUTPUT;

-- Parse embedding from response
SELECT JSON_QUERY(@response, '$.result.data[0].embedding') as embedding;
```

---

## Step 5: Semantic Search Query

### Find similar chunks to a query

```sql
-- @query_embedding is the embedding of the user's search query
DECLARE @query_embedding VECTOR(1536) = CAST(@query_json AS VECTOR(1536));

SELECT TOP 10
    c.id,
    c.text,
    c.section,
    c.page_start,
    c.page_end,
    s.title as source_title,
    s.author,
    VECTOR_DISTANCE('cosine', c.embedding, @query_embedding) as distance
FROM chunks c
JOIN sources s ON c.source_id = s.id
WHERE c.embedding IS NOT NULL
ORDER BY VECTOR_DISTANCE('cosine', c.embedding, @query_embedding);
```

### Python function for semantic search

```python
import json

def semantic_search(cursor, query: str, top_k: int = 10) -> list[dict]:
    """Find chunks semantically similar to query.

    Args:
        cursor: Database cursor
        query: User's search query
        top_k: Number of results to return

    Returns:
        List of matching chunks with metadata
    """
    # Generate embedding for query
    query_embedding = get_embedding(query)
    query_json = json.dumps(query_embedding)

    cursor.execute(
        """
        SELECT TOP (?)
            c.id,
            c.text,
            c.section,
            c.page_start,
            c.page_end,
            s.title as source_title,
            s.author,
            VECTOR_DISTANCE('cosine', c.embedding, CAST(? AS VECTOR(1536))) as distance
        FROM chunks c
        JOIN sources s ON c.source_id = s.id
        WHERE c.embedding IS NOT NULL
        ORDER BY VECTOR_DISTANCE('cosine', c.embedding, CAST(? AS VECTOR(1536)))
        """,
        (top_k, query_json, query_json)
    )

    results = []
    for row in cursor.fetchall():
        results.append({
            "id": row[0],
            "text": row[1],
            "section": row[2],
            "page_start": row[3],
            "page_end": row[4],
            "source_title": row[5],
            "author": row[6],
            "distance": row[7],
        })

    return results
```

---

## Step 6: RAG (Retrieval-Augmented Generation)

Combine semantic search with Claude for synthesis:

```python
import anthropic

def answer_question(query: str, cursor) -> str:
    """Answer question using RAG pattern.

    1. Find relevant chunks via semantic search
    2. Send chunks + query to Claude for synthesis
    3. Return answer with citations
    """
    # Step 1: Retrieve relevant chunks
    chunks = semantic_search(cursor, query, top_k=10)

    # Step 2: Format context for Claude
    context = "\n\n---\n\n".join([
        f"Source: {c['source_title']} by {c['author']} (pages {c['page_start']}-{c['page_end']})\n{c['text']}"
        for c in chunks
    ])

    # Step 3: Query Claude
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Based on the following sources, answer this question: {query}

Sources:
{context}

Provide a comprehensive answer and cite the specific sources used."""
        }]
    )

    return response.content[0].text
```

---

## Cost Estimates

| Item | Cost |
|------|------|
| OpenAI text-embedding-3-small | ~$0.00002 per 1K tokens |
| 100 chunks × 500 tokens each | ~$0.001 total |
| 1000 chunks | ~$0.01 total |
| Query embedding | ~$0.00001 per query |

Embedding cost is negligible. Main costs are Claude API for synthesis.

---

## Performance Considerations

### Current Limitations (Azure SQL Database)

- **No vector indexing yet**: DiskANN is SQL Server 2025 only
- **Brute-force scan**: Every query scans all embeddings
- **Good for small scale**: Works well for <10K chunks

### For Scale (Future)

When DiskANN comes to Azure SQL Database:
```sql
-- Create vector index (SQL Server 2025 / future Azure SQL)
CREATE VECTOR INDEX IX_chunks_embedding
ON chunks(embedding)
WITH (METRIC = 'cosine', TYPE = 'DiskANN');
```

---

## Integration with Current Pipeline

### Updated Ingestion Flow

```
1. Blob uploaded to Azure Storage
2. Azure Function triggers
3. Parse PDF → Extract text
4. Chunk text → Create chunk records
5. NEW: Generate embedding for each chunk
6. Store chunk + embedding in Azure SQL
7. Mark source as COMPLETE
```

### Files to Modify

| File | Changes |
|------|---------|
| `shared/db/models.py` | Add embedding column to schema |
| `functions/shared/storage.py` | Store embeddings with chunks |
| `functions/shared/embeddings.py` | NEW: Embedding generation module |
| `functions/function_app.py` | Add embedding step after chunking |

---

## References

- [Azure SQL Vector Search Samples](https://github.com/Azure-Samples/azure-sql-db-vector-search)
- [Vector Similarity Search with Azure SQL](https://devblogs.microsoft.com/azure-sql/vector-similarity-search-with-azure-sql-database-and-openai/)
- [Semantic Search in Azure SQL](https://erincon01.medium.com/semantic-search-in-sql-azure-practical-example-for-a-customer-support-department-30d87f76e55b)
- [Native Vector Support Announcement](https://devblogs.microsoft.com/azure-sql/announcing-eap-native-vector-support-in-azure-sql-database/)
