"""Shared utilities for Azure Functions.

Exports:
- Parser: PDF parsing with PyMuPDF
- Chunker: Text chunking with page boundaries
- Validation: Input validation and processing states
- Logging: Structured JSON logging
- Embeddings: OpenAI embedding generation
- Concepts: Claude API concept extraction
- Graph: Concept and relationship storage
- Storage: Database operations
"""

from .chunker import Chunk, chunk_by_size, chunk_document
from .concepts import (
    Concept,
    ExtractionResult,
    Relationship,
    extract_concepts_from_chunk,
    find_source_relationships,
)
from .embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    embed_chunks,
    embedding_to_json,
    get_embedding,
    get_embeddings_batch,
)
from .graph import (
    create_covers_edges,
    process_source_concepts,
    source_level_relationship_pass,
    store_chunk_extraction,
)
from .logging_utils import StructuredLogger, structured_logger
from .parser import PageContent, ParsedDocument, detect_file_type, parse_pdf
from .storage import (
    get_chunks_for_source,
    get_source_by_path,
    store_document,
    update_source_status,
)
from .validation import (
    MAX_CHUNK_SIZE,
    MAX_CHUNKS_PER_SOURCE,
    MAX_FILE_SIZE_BYTES,
    MAX_PAGES,
    MIN_TEXT_LENGTH,
    ProcessingStatus,
    ValidationError,
    ValidationResult,
    validate_chunk_count,
    validate_chunk_positions,
    validate_file_size,
    validate_minimum_text,
    validate_page_count,
    validate_pdf_magic_bytes,
)

__all__ = [
    # Parser
    "PageContent",
    "ParsedDocument",
    "parse_pdf",
    "detect_file_type",
    # Chunker
    "Chunk",
    "chunk_document",
    "chunk_by_size",
    # Embeddings
    "get_embedding",
    "get_embeddings_batch",
    "embed_chunks",
    "embedding_to_json",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    # Concepts
    "Concept",
    "Relationship",
    "ExtractionResult",
    "extract_concepts_from_chunk",
    "find_source_relationships",
    # Graph
    "store_chunk_extraction",
    "source_level_relationship_pass",
    "create_covers_edges",
    "process_source_concepts",
    # Storage
    "store_document",
    "update_source_status",
    "get_source_by_path",
    "get_chunks_for_source",
    # Validation
    "ProcessingStatus",
    "ValidationError",
    "ValidationResult",
    "validate_file_size",
    "validate_pdf_magic_bytes",
    "validate_page_count",
    "validate_chunk_count",
    "validate_minimum_text",
    "validate_chunk_positions",
    "MAX_FILE_SIZE_BYTES",
    "MAX_PAGES",
    "MAX_CHUNKS_PER_SOURCE",
    "MAX_CHUNK_SIZE",
    "MIN_TEXT_LENGTH",
    # Logging
    "StructuredLogger",
    "structured_logger",
]
