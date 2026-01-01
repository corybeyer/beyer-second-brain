"""OpenAI embedding generation for semantic search.

Generates embeddings using text-embedding-3-small (1536 dimensions).
Supports single and batch embedding with retry logic.
"""

import json
import os
import time
from typing import TYPE_CHECKING

from openai import OpenAI, RateLimitError, APIError

from .logging_utils import structured_logger

if TYPE_CHECKING:
    from .chunker import Chunk

# Model configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_BATCH_SIZE = 100  # OpenAI supports up to 2048, but smaller batches are safer

# Initialize client lazily
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        _client = OpenAI(api_key=api_key)
    return _client


def get_embedding(text: str, max_retries: int = 3) -> list[float]:
    """Generate embedding for a single text.

    Args:
        text: Text to embed (max ~8000 tokens for text-embedding-3-small)
        max_retries: Number of retry attempts for rate limits

    Returns:
        List of floats (1536 dimensions)

    Raises:
        RateLimitError: If rate limit exceeded after all retries
        APIError: If API call fails after retries
    """
    client = _get_client()

    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(
                input=text,
                model=EMBEDDING_MODEL,
            )
            return response.data[0].embedding

        except RateLimitError:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) * 2  # 2s, 4s, 8s
                structured_logger.warning(
                    "embedding",
                    f"Rate limited, retrying in {wait}s",
                    attempt=attempt + 1,
                )
                time.sleep(wait)
            else:
                raise

        except APIError as e:
            if attempt < max_retries - 1:
                structured_logger.warning(
                    "embedding",
                    f"API error, retrying: {e}",
                    attempt=attempt + 1,
                )
                time.sleep(2)
            else:
                raise

    # Should not reach here, but satisfy type checker
    raise APIError("Max retries exceeded")


def get_embeddings_batch(
    texts: list[str],
    batch_size: int = MAX_BATCH_SIZE,
    max_retries: int = 3,
) -> list[list[float]]:
    """Generate embeddings for multiple texts efficiently.

    Batches requests to OpenAI API for efficiency.
    Handles rate limits with exponential backoff.

    Args:
        texts: List of texts to embed
        batch_size: Number of texts per API call (default 100)
        max_retries: Number of retry attempts for rate limits

    Returns:
        List of embeddings in same order as input texts
    """
    client = _get_client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        for attempt in range(max_retries):
            try:
                response = client.embeddings.create(
                    input=batch,
                    model=EMBEDDING_MODEL,
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

                structured_logger.info(
                    "embedding",
                    f"Generated embeddings for batch {i // batch_size + 1}",
                    batch_start=i,
                    batch_size=len(batch),
                )
                break  # Success, move to next batch

            except RateLimitError:
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 2
                    structured_logger.warning(
                        "embedding",
                        f"Rate limited on batch, retrying in {wait}s",
                        batch_start=i,
                        attempt=attempt + 1,
                    )
                    time.sleep(wait)
                else:
                    raise

            except APIError as e:
                if attempt < max_retries - 1:
                    structured_logger.warning(
                        "embedding",
                        f"API error on batch, retrying: {e}",
                        batch_start=i,
                        attempt=attempt + 1,
                    )
                    time.sleep(2)
                else:
                    raise

    return all_embeddings


def embed_chunks(chunks: list["Chunk"]) -> list["Chunk"]:
    """Add embeddings to all chunks.

    Modifies chunks in-place by adding embedding attribute.

    Args:
        chunks: List of Chunk objects

    Returns:
        Same list of chunks with embeddings added
    """
    if not chunks:
        return chunks

    texts = [chunk.text for chunk in chunks]

    with structured_logger.timed_operation(
        "embedding", f"Generating embeddings for {len(chunks)} chunks"
    ) as ctx:
        embeddings = get_embeddings_batch(texts)
        ctx["chunk_count"] = len(chunks)

    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding

    return chunks


def embedding_to_json(embedding: list[float]) -> str:
    """Convert embedding to JSON string for database storage.

    Args:
        embedding: List of floats

    Returns:
        JSON string representation
    """
    return json.dumps(embedding)
